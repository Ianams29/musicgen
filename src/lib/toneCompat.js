// src/lib/toneCompat.js
let cachedTone = null;

export async function getTone() {
  if (cachedTone) return cachedTone;

  const mod = await import('tone');

  // 1) default 안에만 들어있는 경우와 named 안에만 들어있는 경우 모두 커버
  const ToneNS = { ...(mod.default || {}), ...mod };

  // 2) window.Tone 이 있다면 병합 (UMD 빌드 대비)
  if (typeof window !== 'undefined' && window.Tone) {
    Object.assign(ToneNS, window.Tone);
  }

  // 3) 디버깅 로그 (필요할 때만)
  console.log('[toneCompat] Tone keys:', Object.keys(ToneNS));

  cachedTone = ToneNS;
  return ToneNS;
}

export async function ensureAudioStart(Tone) {
  try {
    if (typeof Tone?.start === 'function') {
      await Tone.start();
      return;
    }
  } catch (_) {}

  try {
    const ctx = Tone?.getContext?.() ?? Tone?.context ?? null;
    if (ctx?.resume) {
      await ctx.resume();
      if (ctx?.state === 'running') return;
    }
    const ac = ctx?.rawContext || ctx?.audioContext;
    if (ac?.resume) await ac.resume();
  } catch (_) {}
}
