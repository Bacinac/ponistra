package main

import (
	"log/slog"
	"os"
	"path/filepath"

	"github.com/pion/webrtc/v4/pkg/media"
)

const (
	// An Opus frame of 20 ms carrying speech takes tens of bytes; one of silence, behind the
	// browser's noise suppression or its DTX, a few.
	loud = 20
	// What ends an utterance: a pause this long, a shorter one once it runs long, or its
	// utmost length; one with less speech than the shortest is no utterance.
	pause    = 800
	breath   = 250
	long     = 30_000
	utmost   = 60_000
	shortest = 400
	// How much before its first loud frame an utterance keeps, for the first syllable's onset.
	before = 200
)

type frame struct {
	at   int64
	data []byte
}

// speech cuts a microphone's track into utterances, each a file of its own read by speech to
// text apart from the others, so that the transcript knows who said what and when.
type speech struct {
	r       *recording
	who     part
	offset  int64
	started bool
	recent  []frame
	out     *webmFile
	name    string
	begin   int64
	spoke   int64
	spoken  int64
}

func (s *speech) heard(at int64, sample *media.Sample) {
	if !s.started {
		s.started, s.offset = true, s.r.since()-at
	}
	if s.out != nil {
		length, quiet := at-s.begin, at-s.spoke
		if quiet >= pause || length >= utmost || (length >= long && quiet >= breath) {
			s.end()
		}
	}
	data := append([]byte(nil), sample.Data...)
	isLoud := len(data) >= loud
	if s.out == nil {
		if !isLoud {
			s.recent = append(s.recent, frame{at, data})
			for len(s.recent) > 0 && at-s.recent[0].at > before {
				s.recent = s.recent[1:]
			}
			return
		}
		s.name = s.r.named("speech")
		out, err := opened(filepath.Join(s.r.folder, s.name), audioEntry(), 4096)
		if err != nil {
			slog.Error("an utterance's file was not opened", "id", s.r.asked.ID, "error", err)
			return
		}
		s.out, s.begin, s.spoke, s.spoken = out, at, at, 0
		if len(s.recent) > 0 {
			s.begin = s.recent[0].at
		}
		for _, kept := range s.recent {
			s.write(kept.at, kept.data)
		}
		s.recent = nil
	}
	s.write(at, data)
	if isLoud {
		s.spoke = at
		s.spoken += sample.Duration.Milliseconds()
	}
}

func (s *speech) write(at int64, data []byte) {
	if err := s.out.write(true, at-s.begin, data); err != nil {
		slog.Error("an utterance stopped being written", "id", s.r.asked.ID, "error", err)
	}
}

func (s *speech) end() {
	if s.out == nil {
		return
	}
	if err := s.out.close(); err != nil {
		slog.Error("an utterance's file was not closed", "id", s.r.asked.ID, "error", err)
	}
	path := s.out.path
	s.out = nil
	if s.spoken < shortest {
		_ = os.Remove(path)
		return
	}
	s.r.note(part{
		Kind: "utterance", File: s.name, Identity: s.who.Identity, Name: s.who.Name,
		Start: s.offset + s.begin, End: s.offset + s.spoke,
	})
}
