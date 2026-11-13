package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/pion/webrtc/v4/pkg/media"
)

func duration(t *testing.T, path string) float64 {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	at := bytes.Index(data, []byte{0x44, 0x89, 0x88})
	if at < 0 {
		t.Fatalf("%s has no duration", path)
	}
	return math.Float64frombits(binary.BigEndian.Uint64(data[at+3 : at+11]))
}

func TestAFileKnowsItsLengthAndIndexesItsClusters(t *testing.T) {
	path := filepath.Join(t.TempDir(), "sound.webm")
	out, err := opened(path, audioEntry(), audioCues)
	if err != nil {
		t.Fatal(err)
	}
	for at := int64(0); at <= 40_000; at += 20 {
		if err := out.write(true, at, bytes.Repeat([]byte{1}, 40)); err != nil {
			t.Fatal(err)
		}
	}
	if err := out.close(); err != nil {
		t.Fatal(err)
	}
	if got := duration(t, path); got != 40_000 {
		t.Fatalf("duration %v, want 40000", got)
	}
	data, _ := os.ReadFile(path)
	cues := bytes.LastIndex(data, []byte{0x1C, 0x53, 0xBB, 0x6B})
	if cues < 0 || data[cues+4] == 0x88 {
		t.Fatal("the file has no index of its clusters")
	}
}

func TestTheClockCountsFromTheFirstSampleAndAcrossTheWrap(t *testing.T) {
	c := clock{rate: 48_000}
	start := uint32(math.MaxUint32 - 480)
	if got := c.at(start); got != 0 {
		t.Fatalf("first %d", got)
	}
	if got := c.at(start + 960); got != 20 {
		t.Fatalf("across the wrap %d, want 20", got)
	}
	if got := c.at(start + 480); got != 20 {
		t.Fatalf("a late sample moved the clock back to %d", got)
	}
}

func TestAKeyframeGivesItsSize(t *testing.T) {
	frame := []byte{0x10, 0, 0, 0x9d, 0x01, 0x2a, 0x80, 0x02, 0x68, 0x01}
	if key, width, height := keyframe(frame); !key || width != 640 || height != 360 {
		t.Fatalf("keyframe %v %dx%d", key, width, height)
	}
	if key, _, _ := keyframe([]byte{0x11, 0, 0, 0, 0, 0, 0, 0, 0, 0}); key {
		t.Fatal("an interframe taken for a keyframe")
	}
}

func readParts(t *testing.T, folder string) []part {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(folder, "parts.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	var found []part
	for _, line := range bytes.Split(bytes.TrimSpace(data), []byte("\n")) {
		var each part
		if err := json.Unmarshal(line, &each); err != nil {
			t.Fatal(err)
		}
		found = append(found, each)
	}
	return found
}

func TestSpeechIsCutIntoUtterancesAtItsPauses(t *testing.T) {
	folder := t.TempDir()
	parts, err := os.OpenFile(filepath.Join(folder, "parts.jsonl"), os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	r := &recording{asked: started{ID: "x"}, folder: folder, began: time.Now(), parts: parts}
	s := &speech{r: r, who: part{Identity: "7.ab", Name: "Ana"}}
	loud := &media.Sample{Data: bytes.Repeat([]byte{1}, 60), Duration: 20 * time.Millisecond}
	quiet := &media.Sample{Data: []byte{1, 2, 3}, Duration: 20 * time.Millisecond}
	heard := func(from, to int64, sample *media.Sample) {
		for at := from; at < to; at += 20 {
			s.heard(at, sample)
		}
	}
	heard(0, 1000, quiet)
	heard(1000, 3000, loud)
	heard(3000, 4000, quiet)
	heard(4000, 4200, loud)
	heard(4200, 5200, quiet)
	heard(5200, 75_200, loud)
	s.end()
	parts.Close()
	var said []part
	for _, each := range readParts(t, folder) {
		if each.Kind == "utterance" {
			said = append(said, each)
		}
	}
	if len(said) != 3 {
		t.Fatalf("%d utterances, want 3: %+v", len(said), said)
	}
	first := said[0].Start - s.offset
	if first != 780 || said[0].End-s.offset != 2980 {
		t.Fatalf("the first utterance runs %d-%d", first, said[0].End-s.offset)
	}
	if said[1].End-said[1].Start != utmost-20 {
		t.Fatalf("a long utterance ran %d ms", said[1].End-said[1].Start)
	}
	if said[0].Identity != "7.ab" || said[0].Name != "Ana" {
		t.Fatalf("the utterance names %q %q", said[0].Identity, said[0].Name)
	}
	for _, each := range said {
		if d := duration(t, filepath.Join(folder, each.File)); d <= 0 {
			t.Fatalf("%s lasts %v", each.File, d)
		}
	}
	entries, _ := os.ReadDir(folder)
	if len(entries) != 4 {
		t.Fatalf("%d files: the one too short to be an utterance was kept", len(entries))
	}
}

func TestAManifestIsMadeOfTheNotedPartsOfARecordingCutOff(t *testing.T) {
	folder := filepath.Join(t.TempDir(), "4b0f3c1e-4b1f-4f3c-9b1e-3c1e4b1f4f3c")
	if err := os.Mkdir(folder, 0o700); err != nil {
		t.Fatal(err)
	}
	parts, _ := os.Create(filepath.Join(folder, "parts.jsonl"))
	r := &recording{folder: folder, parts: parts}
	r.note(part{Kind: "began", Start: 1_700_000_000_000})
	r.note(part{Kind: "track", File: "0001-audio.webm", Identity: "7.ab", Media: "audio", Start: 100})
	r.note(part{Kind: "track", File: "0002-video.webm", Identity: "7.ab", Media: "video", Start: 300})
	r.note(part{Kind: "end", File: "0001-audio.webm", End: 9000})
	r.note(part{Kind: "utterance", File: "0003-speech.webm", Identity: "7.ab", Start: 500, End: 2000})
	parts.Close()
	if err := os.WriteFile(filepath.Join(folder, "0002-video.webm"), []byte{1}, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := cutOff(folder); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(folder, "manifest.json"))
	if err != nil {
		t.Fatal(err)
	}
	var made manifest
	if err := json.Unmarshal(data, &made); err != nil {
		t.Fatal(err)
	}
	if len(made.Tracks) != 2 || made.Tracks[0].End != 9000 || made.Tracks[1].End <= made.Tracks[1].Start {
		t.Fatalf("tracks %+v", made.Tracks)
	}
	if len(made.Utterances) != 1 || !made.names("0003-speech.webm") || made.names("parts.jsonl") {
		t.Fatalf("utterances %+v", made.Utterances)
	}
}
