package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/livekit/protocol/livekit"
	lksdk "github.com/livekit/server-sdk-go/v2"
	"github.com/pion/webrtc/v4"
)

// How long a room may stay without anyone in it before the recording ends: a page reloaded
// or a network changed comes back within it.
const empty = 60 * time.Second

// How long starting waits for the tracks already sent to be written, so that a recording
// reported as running holds them: a picture waits for its keyframe.
const settle = 5 * time.Second

// part is a line of parts.jsonl, written as the recording goes, so that a crash leaves what
// was written readable.
type part struct {
	Kind     string `json:"kind"`
	File     string `json:"file,omitempty"`
	Identity string `json:"identity,omitempty"`
	Name     string `json:"name,omitempty"`
	Media    string `json:"media,omitempty"`
	Source   string `json:"source,omitempty"`
	Codec    string `json:"codec,omitempty"`
	Start    int64  `json:"start"`
	End      int64  `json:"end"`
}

// manifest is what a recording made: each track as a file with its place on the recording's
// time, in milliseconds from its start, and each utterance as a file of its own.
type manifest struct {
	ID         string    `json:"id"`
	Began      time.Time `json:"began"`
	Ended      time.Time `json:"ended"`
	Tracks     []part    `json:"tracks"`
	Utterances []part    `json:"utterances"`
	Skipped    []part    `json:"skipped"`
}

func (m manifest) names(name string) bool {
	for _, each := range append(m.Tracks, m.Utterances...) {
		if each.File == name {
			return true
		}
	}
	return false
}

type recording struct {
	asked   started
	folder  string
	began   time.Time
	room    *lksdk.Room
	ended   func()
	lines   sync.Mutex
	parts   *os.File
	writers sync.WaitGroup
	once    sync.Once
	counted atomic.Int64
	waiting sync.Mutex
	alone   *time.Timer
	taken   chan struct{}
}

func record(asked started, folder string, ended func()) (*recording, error) {
	parts, err := os.OpenFile(filepath.Join(folder, "parts.jsonl"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return nil, err
	}
	r := &recording{
		asked: asked, folder: folder, began: time.Now(), parts: parts, ended: ended,
		taken: make(chan struct{}, 256),
	}
	r.note(part{Kind: "began", Start: r.began.UnixMilli()})
	callback := lksdk.NewRoomCallback()
	callback.OnTrackSubscribed = r.subscribed
	callback.OnParticipantConnected = func(*lksdk.RemoteParticipant) { r.company() }
	callback.OnParticipantDisconnected = func(*lksdk.RemoteParticipant) { r.company() }
	callback.OnDisconnected = func() { go r.finish(true) }
	room, err := lksdk.ConnectToRoomWithToken(asked.URL, asked.Token, callback, lksdk.WithAutoSubscribe(true))
	if err != nil {
		parts.Close()
		return nil, err
	}
	r.room = room
	r.company()
	r.settled()
	return r, nil
}

// settled waits until every track sent when the recorder joined is being written, or settle.
func (r *recording) settled() {
	sent := 0
	for _, participant := range r.room.GetRemoteParticipants() {
		for _, publication := range participant.TrackPublications() {
			if !publication.IsMuted() {
				sent++
			}
		}
	}
	deadline := time.After(settle)
	for ; sent > 0; sent-- {
		select {
		case <-r.taken:
		case <-deadline:
			slog.Warn("tracks were not yet written when the recording started", "id", r.asked.ID, "missing", sent)
			return
		}
	}
}

func (r *recording) took() {
	select {
	case r.taken <- struct{}{}:
	default:
	}
}

func (r *recording) since() int64 {
	return time.Since(r.began).Milliseconds()
}

func (r *recording) named(kind string) string {
	return fmt.Sprintf("%04d-%s.webm", r.counted.Add(1), kind)
}

func (r *recording) note(line part) {
	data, _ := json.Marshal(line)
	r.lines.Lock()
	defer r.lines.Unlock()
	if _, err := r.parts.Write(append(data, '\n')); err != nil {
		slog.Error("a part of the recording was not noted", "id", r.asked.ID, "error", err)
	}
}

// company ends the recording once the room has stayed without anyone in it.
func (r *recording) company() {
	r.waiting.Lock()
	defer r.waiting.Unlock()
	if r.room == nil {
		return
	}
	if len(r.room.GetRemoteParticipants()) > 0 {
		if r.alone != nil {
			r.alone.Stop()
			r.alone = nil
		}
		return
	}
	if r.alone == nil {
		r.alone = time.AfterFunc(empty, func() {
			if len(r.room.GetRemoteParticipants()) == 0 {
				r.finish(true)
			}
		})
	}
}

func (r *recording) subscribed(track *webrtc.TrackRemote, publication *lksdk.RemoteTrackPublication, participant *lksdk.RemoteParticipant) {
	who := part{
		Identity: participant.Identity(),
		Name:     participant.Name(),
		Source:   strings.ToLower(publication.Source().String()),
		Codec:    strings.ToLower(track.Codec().MimeType),
	}
	switch who.Codec {
	case "audio/opus":
		who.Media = "audio"
	case "video/vp8":
		who.Media = "video"
		publication.SetVideoQuality(livekit.VideoQuality_HIGH)
	default:
		who.Kind, who.Media = "skipped", track.Kind().String()
		who.Start = r.since()
		r.note(who)
		r.took()
		slog.Error("a track in a codec WebM does not hold was not recorded", "id", r.asked.ID, "codec", who.Codec)
		return
	}
	r.writers.Add(1)
	go func() {
		defer r.writers.Done()
		written(r, track, who, func() { participant.WritePLI(track.SSRC()) })
	}()
}

// finish leaves the room, waits for every file to be closed and writes the manifest; told,
// the backend hears of it.
func (r *recording) finish(told bool) {
	r.once.Do(func() {
		r.waiting.Lock()
		if r.alone != nil {
			r.alone.Stop()
		}
		r.waiting.Unlock()
		if r.room != nil {
			r.room.Disconnect()
		}
		r.writers.Wait()
		r.parts.Close()
		if err := cutOff(r.folder); err != nil {
			slog.Error("the manifest was not written", "id", r.asked.ID, "error", err)
		}
		slog.Info("recording ended", "id", r.asked.ID, "told", told)
		if told {
			r.ended()
		} else {
			running.Delete(r.asked.ID)
		}
	})
}

// cutOff writes the manifest from the parts noted, a track never closed ending where its
// file was last written.
func cutOff(folder string) error {
	opened, err := os.Open(filepath.Join(folder, "parts.jsonl"))
	if err != nil {
		return err
	}
	defer opened.Close()
	kept := manifest{ID: filepath.Base(folder), Ended: time.Now(), Tracks: []part{}, Utterances: []part{}, Skipped: []part{}}
	ends := map[string]int64{}
	var tracks []part
	lines := bufio.NewScanner(opened)
	lines.Buffer(make([]byte, 64*1024), 1024*1024)
	for lines.Scan() {
		var line part
		if json.Unmarshal(lines.Bytes(), &line) != nil {
			continue
		}
		switch line.Kind {
		case "began":
			kept.Began = time.UnixMilli(line.Start)
		case "track":
			tracks = append(tracks, line)
		case "end":
			ends[line.File] = line.End
		case "utterance":
			kept.Utterances = append(kept.Utterances, line)
		case "skipped":
			kept.Skipped = append(kept.Skipped, line)
		}
	}
	for _, track := range tracks {
		if end, ok := ends[track.File]; ok {
			track.End = end
		} else if info, err := os.Stat(filepath.Join(folder, track.File)); err == nil {
			track.End = info.ModTime().Sub(kept.Began).Milliseconds()
		} else {
			continue
		}
		kept.Tracks = append(kept.Tracks, track)
	}
	return writeJSON(filepath.Join(folder, "manifest.json"), kept)
}
