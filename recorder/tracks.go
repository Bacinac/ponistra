package main

import (
	"log/slog"
	"os"
	"path/filepath"
	"time"

	"github.com/at-wat/ebml-go/mkvcore"
	"github.com/at-wat/ebml-go/webm"
	"github.com/livekit/server-sdk-go/v2/pkg/samplebuilder"
	"github.com/pion/rtp/codecs"
	"github.com/pion/webrtc/v4"
	"github.com/pion/webrtc/v4/pkg/media"
)

const (
	// How many packets may wait for one late before it is given up on.
	videoLate = 1000
	audioLate = 200
	// The room for each file's index of its keyframes and clusters, ahead of its picture or
	// sound: an index larger is thinned to fit.
	videoCues = 128 * 1024
	audioCues = 16 * 1024
)

// webmFile is one track written into a WebM file, its timestamps in milliseconds from the
// file's first sample, with an index for a player to seek by.
type webmFile struct {
	path   string
	blocks webm.BlockWriteCloser
}

func opened(path string, entry webm.TrackEntry, cues int) (*webmFile, error) {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR|os.O_TRUNC, 0o600)
	if err != nil {
		return nil, err
	}
	blocks, err := webm.NewSimpleBlockWriter(file, []webm.TrackEntry{entry},
		mkvcore.WithSegmentInfo(&webm.Info{TimecodeScale: 1000000, MuxingApp: "Ponistra", WritingApp: "Ponistra"}),
		mkvcore.WithSeekHead(true),
		mkvcore.WithCues(cues),
	)
	if err != nil {
		file.Close()
		return nil, err
	}
	return &webmFile{path: path, blocks: blocks[0]}, nil
}

func audioEntry() webm.TrackEntry {
	return webm.TrackEntry{
		Name: "Audio", TrackNumber: 1, TrackUID: 1, CodecID: "A_OPUS", TrackType: 2,
		DefaultDuration: 20000000,
		Audio:           &webm.Audio{SamplingFrequency: 48000, Channels: 2},
	}
}

func videoEntry(width, height int) webm.TrackEntry {
	return webm.TrackEntry{
		Name: "Video", TrackNumber: 1, TrackUID: 1, CodecID: "V_VP8", TrackType: 1,
		Video: &webm.Video{PixelWidth: uint64(width), PixelHeight: uint64(height)},
	}
}

func (f *webmFile) write(keyframe bool, at int64, data []byte) error {
	_, err := f.blocks.Write(keyframe, at, data)
	return err
}

func (f *webmFile) close() error {
	return f.blocks.Close()
}

// clock turns a track's RTP timestamps into milliseconds from its first sample.
type clock struct {
	rate    int64
	started bool
	last    uint32
	elapsed int64
}

func (c *clock) at(timestamp uint32) int64 {
	if !c.started {
		c.started, c.last = true, timestamp
		return 0
	}
	if step := int32(timestamp - c.last); step > 0 {
		c.elapsed += int64(step)
		c.last = timestamp
	}
	return c.elapsed * 1000 / c.rate
}

// keyframe tells a VP8 frame that starts a picture of its own, and its size.
func keyframe(data []byte) (bool, int, int) {
	if len(data) < 10 || data[0]&0x1 != 0 {
		return false, 0, 0
	}
	raw := uint(data[6]) | uint(data[7])<<8 | uint(data[8])<<16 | uint(data[9])<<24
	return true, int(raw & 0x3FFF), int((raw >> 16) & 0x3FFF)
}

// written writes the track into its file while it lasts, and a microphone's speech into an
// utterance file for each stretch of it.
func written(r *recording, track *webrtc.TrackRemote, who part, picture func()) {
	var builder *samplebuilder.SampleBuilder
	if who.Media == "audio" {
		builder = samplebuilder.New(audioLate, &codecs.OpusPacket{}, track.Codec().ClockRate)
	} else {
		builder = samplebuilder.New(videoLate, &codecs.VP8Packet{}, track.Codec().ClockRate,
			samplebuilder.WithPacketDroppedHandler(picture))
	}
	times := clock{rate: int64(track.Codec().ClockRate)}
	var out *webmFile
	var talk *speech
	if who.Media == "audio" && who.Source == "microphone" {
		talk = &speech{r: r, who: who}
	}
	if who.Media == "video" {
		picture()
	}
	defer func() {
		if talk != nil {
			talk.end()
		}
		if out != nil {
			if err := out.close(); err != nil {
				slog.Error("a track's file was not closed", "id", r.asked.ID, "file", out.path, "error", err)
			}
			r.note(part{Kind: "end", File: filepath.Base(out.path), End: r.since()})
		}
	}()
	asked := time.Now()
	for {
		packet, _, err := track.ReadRTP()
		if err != nil {
			return
		}
		builder.Push(packet)
		for {
			sample, timestamp := builder.PopWithTimestamp()
			if sample == nil {
				break
			}
			at := times.at(timestamp)
			if out == nil {
				var err error
				out, err = first(r, who, sample)
				if err != nil {
					slog.Error("a track's file was not opened", "id", r.asked.ID, "error", err)
					return
				}
				if out == nil {
					if time.Since(asked) > time.Second {
						picture()
						asked = time.Now()
					}
					times = clock{rate: times.rate}
					continue
				}
			}
			isKey := who.Media == "audio"
			if !isKey {
				isKey, _, _ = keyframe(sample.Data)
			}
			if err := out.write(isKey, at, sample.Data); err != nil {
				slog.Error("a track's file stopped being written", "id", r.asked.ID, "error", err)
				return
			}
			if talk != nil {
				talk.heard(at, sample)
			}
		}
	}
}

// first opens the track's file at its first sample, a picture's only at a keyframe, which
// gives its size; nil while a picture waits for one.
func first(r *recording, who part, sample *media.Sample) (*webmFile, error) {
	entry, cues := audioEntry(), audioCues
	if who.Media == "video" {
		isKey, width, height := keyframe(sample.Data)
		if !isKey || width == 0 || height == 0 {
			return nil, nil
		}
		entry, cues = videoEntry(width, height), videoCues
	}
	name := r.named(who.Media)
	out, err := opened(filepath.Join(r.folder, name), entry, cues)
	if err != nil {
		return nil, err
	}
	who.Kind, who.File, who.Start = "track", name, r.since()
	r.note(who)
	r.took()
	return out, nil
}
