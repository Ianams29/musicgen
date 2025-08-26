// src/components/beat/SampleKit.js
// Tone는 import 하지 않습니다. toneCompat가 전역(window.Tone)을 로드합니다.
import { getTone } from '../../lib/toneCompat';

// dB → linear
const dbToGain = (db) => Math.pow(10, db / 20);

export async function createKit({ volume = -6 } = {}) {
  const Tone = await getTone();

  // 각 트리거가 공통으로 거칠 마스터 게인 (곡 전체 볼륨조절용)
  const master = new Tone.Gain(dbToGain(volume)).toDestination();

  // ---- 단순 킥: 사인파 + 피치 드롭 + 짧은 앰프 엔벨로프
  function triggerKick(time) {
    const osc = new Tone.Oscillator(120, 'sine');
    const amp = new Tone.Gain(0);

    osc.connect(amp);
    amp.connect(master);

    osc.start(time);

    // 앰프 엔벨로프
    amp.gain.setValueAtTime(0.001, time);
    amp.gain.exponentialRampToValueAtTime(0.9, time + 0.004);
    amp.gain.exponentialRampToValueAtTime(0.0001, time + 0.18);

    // 피치 드롭
    osc.frequency.setValueAtTime(120, time);
    osc.frequency.exponentialRampToValueAtTime(50, time + 0.18);

    osc.stop(time + 0.25);

    // 간단 정리 (살짝 여유)
    setTimeout(() => {
      try { osc.dispose(); amp.dispose(); } catch {}
    }, 350);
  }

  // ---- 스네어: 화이트 노이즈 + 짧은 앰프 + 하이패스/밴드패스
  function triggerSnare(time) {
    const noiseSrc = Tone.Noise ? new Tone.Noise('white') : null;

    if (noiseSrc) {
      const hp = new Tone.Filter(800, 'highpass');
      const bp = new Tone.Filter(1800, 'bandpass');
      const amp = new Tone.Gain(0);

      noiseSrc.connect(hp).connect(bp).connect(amp).connect(master);

      noiseSrc.start(time);

      amp.gain.setValueAtTime(0.001, time);
      amp.gain.exponentialRampToValueAtTime(0.8, time + 0.003);
      amp.gain.exponentialRampToValueAtTime(0.0001, time + 0.12);

      noiseSrc.stop(time + 0.15);

      setTimeout(() => {
        try { noiseSrc.dispose(); hp.dispose(); bp.dispose(); amp.dispose(); } catch {}
      }, 300);
    } else {
      // 노이즈가 없는 매우 제한적인 빌드일 경우: 고주파 사각파로 근사
      const osc = new Tone.Oscillator(1000, 'square');
      const amp = new Tone.Gain(0);
      const hp = new Tone.Filter(800, 'highpass');

      osc.connect(hp).connect(amp).connect(master);

      osc.start(time);
      amp.gain.setValueAtTime(0.001, time);
      amp.gain.exponentialRampToValueAtTime(0.6, time + 0.003);
      amp.gain.exponentialRampToValueAtTime(0.0001, time + 0.09);
      osc.stop(time + 0.12);

      setTimeout(() => {
        try { osc.dispose(); hp.dispose(); amp.dispose(); } catch {}
      }, 250);
    }
  }

  // ---- 하이햇: 화이트 노이즈 + 하이패스 + 매우 짧은 앰프
  function triggerHat(time) {
    if (Tone.Noise) {
      const noise = new Tone.Noise('white');
      const hp = new Tone.Filter(7000, 'highpass');
      const amp = new Tone.Gain(0);

      noise.connect(hp).connect(amp).connect(master);

      noise.start(time);
      amp.gain.setValueAtTime(0.001, time);
      amp.gain.exponentialRampToValueAtTime(0.5, time + 0.001);
      amp.gain.exponentialRampToValueAtTime(0.0001, time + 0.05);
      noise.stop(time + 0.06);

      setTimeout(() => {
        try { noise.dispose(); hp.dispose(); amp.dispose(); } catch {}
      }, 180);
    } else {
      // 노이즈가 없다면 초고역 사각파 클릭
      const osc = new Tone.Oscillator(8000, 'square');
      const amp = new Tone.Gain(0);

      osc.connect(amp).connect(master);

      osc.start(time);
      amp.gain.setValueAtTime(0.001, time);
      amp.gain.exponentialRampToValueAtTime(0.4, time + 0.001);
      amp.gain.exponentialRampToValueAtTime(0.0001, time + 0.03);
      osc.stop(time + 0.04);

      setTimeout(() => {
        try { osc.dispose(); amp.dispose(); } catch {}
      }, 120);
    }
  }

  return {
    trigger(track, time) {
      if (track === 'kick') return triggerKick(time);
      if (track === 'snare') return triggerSnare(time);
      if (track === 'hat') return triggerHat(time);
    },
    dispose() {
      try { master.dispose?.(); } catch {}
    },
  };
}

export default createKit;
