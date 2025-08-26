// src/pages/MusicConversion.js
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Container, Grid, Paper, Typography } from '@mui/material';
import { MusicNote } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

import TransportBar from '../components/beat/TransportBar';
import BeatGrid from '../components/beat/BeatGrid';
import BlendPad from '../components/beat/BlendPad';
import { createKit } from '../components/beat/SampleKit';
import { PRESETS, clonePattern } from '../components/beat/presets';
import { bufferToWavBlob, downloadBlob } from '../utils/audioExport';
import { getTone, ensureAudioStart } from '../lib/toneCompat';

const colors = {
  background: '#0A0A0A',
  cardBg: '#1A1A1A',
  primary: '#50E3C2',
  accent: '#2DD4BF',
  text: '#FFFFFF',
  textLight: '#CCCCCC',
  border: '#333333',
};

const tracks = ['kick', 'snare', 'hat'];
const STEPS = 16;

function defaultPattern() {
  return clonePattern(PRESETS['Four on the floor']);
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const blobToDataURL = (blob) =>
  new Promise((resolve) => {
    const fr = new FileReader();
    fr.onloadend = () => resolve(fr.result);
    fr.readAsDataURL(blob);
  });

function isSilentBuffer(audioBuffer, threshold = 1e-4) {
  let peak = 0;
  const { numberOfChannels, length } = audioBuffer;
  const stride = Math.max(1, Math.floor(length / 5000));
  for (let ch = 0; ch < numberOfChannels; ch++) {
    const data = audioBuffer.getChannelData(ch);
    for (let i = 0; i < length; i += stride) {
      const v = Math.abs(data[i]);
      if (v > peak) peak = v;
      if (peak >= threshold) return false;
    }
  }
  return true;
}

export default function MusicConversion() {
  const navigate = useNavigate();

  const [pattern, setPattern] = useState(defaultPattern);
  const [currentStep, setCurrentStep] = useState(-1);
  const [bpm, setBpm] = useState(96);
  const [bars, setBars] = useState(2);

  const [busy, setBusy] = useState(false);
  const [busyMsg, setBusyMsg] = useState('');

  const [corners, setCorners] = useState({
    A: clonePattern(PRESETS['Four on the floor']),
    B: clonePattern(PRESETS['Busy Hats']),
    C: clonePattern(PRESETS['Minimal']),
    D: clonePattern(PRESETS['Funk']),
  });

  const kitRef = useRef(null);
  const seqRefs = useRef({});

  // Transport BPM 동기화
  useEffect(() => {
    let mounted = true;
    (async () => {
      const Tone = await getTone();
      if (!mounted) return;
      if (Tone?.Transport?.bpm?.value != null) {
        Tone.Transport.bpm.value = bpm;
      }
    })();
    return () => { mounted = false; };
  }, [bpm]);

  const onToggle = (track, step) => {
    setPattern((p) => {
      const copy = { ...p, [track]: [...p[track]] };
      copy[track][step] = !copy[track][step];
      return copy;
    });
  };

  const stopAll = async () => {
    const Tone = await getTone();
    Tone?.Transport?.stop?.();
    if (Tone?.Transport) Tone.Transport.position = 0;
    setCurrentStep(-1);
    Object.values(seqRefs.current).forEach((s) => s?.dispose?.());
    seqRefs.current = {};
    kitRef.current?.dispose?.();
    kitRef.current = null;
  };

  const startPlay = async () => {
    const Tone = await getTone();
    await ensureAudioStart(Tone);

    await stopAll();
    kitRef.current = await createKit({ volume: -6 });

    tracks.forEach((t) => {
      const seq = new Tone.Sequence(
        (time, i) => {
          if (pattern[t][i]) kitRef.current.trigger(t, time);
          setTimeout(() => setCurrentStep(i), 0);
        },
        Array.from({ length: STEPS }, (_, i) => i),
        '16n'
      );
      seq.start(0);
      seqRefs.current[t] = seq;
    });

    if (Tone?.Transport?.bpm?.value != null) {
      Tone.Transport.bpm.value = bpm;
    }
    Tone?.Transport?.start?.('+0.03');
  };

  // 오프라인 렌더 (빠르고 클릭 후 바로 WAV 생성)
  const renderBeatOffline = async () => {
    const Tone = await getTone();
    const secondsPerBeat = 60 / bpm;
    const totalSec = Math.max(1, bars) * (secondsPerBeat * 4);

    const audioBuffer = await Tone.Offline(() => {
      // ⚠️ Tone 전역(UMD) 클래스를 사용
      const kick = new Tone.MembraneSynth().toDestination();
      const snare = new Tone.NoiseSynth().toDestination();
      const hat = new Tone.MetalSynth().toDestination();

      if (kick?.volume) kick.volume.value = -6;
      if (snare?.volume) snare.volume.value = -6;
      if (hat?.volume) hat.volume.value = -6;

      tracks.forEach((t) => {
        const seq = new Tone.Sequence(
          (time, i) => {
            if (pattern[t][i]) {
              if (t === 'kick') kick.triggerAttackRelease('C1', '8n', time);
              if (t === 'snare') snare.triggerAttackRelease('8n', time);
              if (t === 'hat') hat.triggerAttackRelease('16n', time);
            }
          },
          Array.from({ length: STEPS }, (_, i) => i),
          '16n'
        );
        seq.start(0);
      });

      if (Tone?.Transport?.bpm?.value != null) {
        Tone.Transport.bpm.value = bpm;
      }
      Tone?.Transport?.start?.(0);
    }, totalSec);

    return audioBuffer;
  };

  // 실시간 녹음(오프라인 실패/무음 시 폴백)
  const recordCurrentBeatToWavBlob = async () => {
    const Tone = await getTone();

    await ensureAudioStart(Tone);
    await stopAll();

    kitRef.current = await createKit({ volume: -6 });
    tracks.forEach((t) => {
      const seq = new Tone.Sequence(
        (time, i) => {
          if (pattern[t][i]) kitRef.current.trigger(t, time);
        },
        Array.from({ length: STEPS }, (_, i) => i),
        '16n'
      );
      seq.start(0);
      seqRefs.current[t] = seq;
    });

    if (Tone?.Transport?.bpm?.value != null) {
      Tone.Transport.bpm.value = bpm;
    }

    const recorder = new Tone.Recorder();
    Tone.Destination.connect(recorder);
    recorder.start();
    Tone?.Transport?.start?.('+0.03');

    const secondsPerBeat = 60 / bpm;
    const totalSec = Math.max(1, bars) * (secondsPerBeat * 4);
    await wait(totalSec * 1000 + 200);

    const wavBlob = await recorder.stop();
    Tone.Destination.disconnect(recorder);
    await stopAll();
    return wavBlob;
  };

  // 하이브리드: 오프라인 우선 → 실패/무음이면 실시간
  const renderBeatToWavBlob = async () => {
    try {
      setBusy(true);
      setBusyMsg('내보내는 중...');
      const buf = await renderBeatOffline();
      if (!isSilentBuffer(buf)) {
        const wav = await bufferToWavBlob(buf);
        setBusy(false);
        setBusyMsg('');
        return wav;
      }
      console.warn('[Beat] Offline buffer looked silent. Falling back to Recorder...');
    } catch (e) {
      console.warn('[Beat] Offline render failed, fallback to Recorder.', e);
    }
    setBusyMsg('실시간 녹음 중...');
    const wav = await recordCurrentBeatToWavBlob();
    setBusy(false);
    setBusyMsg('');
    return wav;
  };

  const exportWav = async () => {
    const wavBlob = await renderBeatToWavBlob();
    downloadBlob(wavBlob, `my-beat-${bpm}bpm-${bars}bars.wav`);
  };

  const sendToGenerate = async () => {
    setBusy(true);
    setBusyMsg('보내는 중...');
    const wavBlob = await renderBeatToWavBlob();
    const dataUrl = await blobToDataURL(wavBlob);
    setBusy(false);
    setBusyMsg('');
    sessionStorage.setItem('inlineReferenceAudio', dataUrl);
    navigate('/generate');
  };

  const colorsMemo = useMemo(() => colors, []);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: colorsMemo.background, py: 6 }}>
      <Container maxWidth="lg">
        <Typography
          variant="h4"
          sx={{ color: colorsMemo.text, fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center' }}
        >
          <MusicNote sx={{ mr: 1, color: colorsMemo.primary }} />
          비트 만들기 (Beat Maker)
        </Typography>

        <Grid container spacing={4}>
          <Grid item xs={12} md={6}>
            <Paper
              elevation={0}
              sx={{ bgcolor: colorsMemo.cardBg, p: 3, borderRadius: 3, border: `1px solid ${colorsMemo.border}` }}
            >
              <Typography variant="h6" sx={{ color: colorsMemo.text, fontWeight: 600, mb: 2 }}>
                패드 블렌딩
              </Typography>
              <BlendPad
                colors={colorsMemo}
                corners={corners}
                onChangeCorners={setCorners}
                onBlend={(mixed) => setPattern(mixed)}
              />
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper
              elevation={0}
              sx={{ bgcolor: colorsMemo.cardBg, p: 3, borderRadius: 3, border: `1px solid ${colorsMemo.border}` }}
            >
              <TransportBar
                bpm={bpm}
                bars={bars}
                onChangeBpm={setBpm}
                onChangeBars={setBars}
                onPlay={startPlay}
                onStop={stopAll}
                onClear={() =>
                  setPattern({ kick: Array(16).fill(false), snare: Array(16).fill(false), hat: Array(16).fill(false) })
                }
                onExport={exportWav}
                onSendToGenerate={sendToGenerate}
                busy={busy}
                busyMsg={busyMsg}
              />

              <Box sx={{ mt: 3 }}>
                <BeatGrid pattern={pattern} currentStep={currentStep} onToggle={onToggle} />
              </Box>

              <Typography variant="body2" sx={{ mt: 2, color: colorsMemo.textLight }}>
                팁: 패드의 위치를 바꾸면 4개 코너 프리셋을 섞어 새 패턴이 만들어져요. 그리드에서 직접 찍어도 됩니다.
              </Typography>
            </Paper>
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
}
