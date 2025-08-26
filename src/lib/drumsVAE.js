// src/lib/drumsVAE.js
import * as tf from '@tensorflow/tfjs';
import { loadMagenta } from './magentaCompat';

// 공개 체크포인트(2마디 드럼 VAE)
const CHECKPOINT =
  'https://storage.googleapis.com/magentadata/js/checkpoints/music_vae/drums_2bar_lokl_small';

let vae = null;
let ready = false;

export async function loadDrumsVAE(checkpointUrl = CHECKPOINT) {
  if (vae && ready) return vae;
  const { MusicVAE } = await loadMagenta();
  vae = new MusicVAE(checkpointUrl);
  await vae.initialize();
  ready = true;
  return vae;
}

// GM 드럼 피치
const KICK = 36, SNARE = 38, HAT = 42;

// 16스텝 패턴 -> 2마디(32스텝) NoteSequence
export async function patternToNoteSequence(pattern, bars = 2, stepsPerBar = 16, qpm = 120) {
  const { sequences } = await loadMagenta();
  const total = bars * stepsPerBar;

  // 16분음표 해상도(stepsPerQuarter=4)
  const seq = sequences.createQuantizedNoteSequence(4);
  seq.tempos = [{ qpm }];

  const map = { kick: KICK, snare: SNARE, hat: HAT };
  for (const [name, pitch] of Object.entries(map)) {
    const arr = pattern[name] || [];
    for (let b = 0; b < bars; b++) {
      for (let i = 0; i < stepsPerBar; i++) {
        if (arr[i]) {
          const step = b * stepsPerBar + i; // 0..31
          seq.notes.push({
            pitch,
            quantizedStartStep: step,
            quantizedEndStep: step + 1,
            isDrum: true,
            velocity: 100,
          });
        }
      }
    }
  }
  seq.totalQuantizedSteps = total;
  return seq;
}

// NoteSequence -> 16스텝 패턴(첫 1마디만)
export function noteSequenceToPattern(seq, stepsOut = 16) {
  const pat = {
    kick: Array(stepsOut).fill(false),
    snare: Array(stepsOut).fill(false),
    hat: Array(stepsOut).fill(false),
  };
  const back = { [KICK]: 'kick', [SNARE]: 'snare', [HAT]: 'hat' };
  for (const n of seq.notes || []) {
    if (!n.isDrum) continue;
    const tr = back[n.pitch];
    if (!tr) continue;
    const step = (n.quantizedStartStep || 0) % stepsOut;
    pat[tr][step] = true;
  }
  return pat;
}

// 코너 4개 -> 잠재벡터 4개
export async function encodeCorners(corners, qpm = 120) {
  const model = await loadDrumsVAE();
  const seqs = await Promise.all(
    ['A','B','C','D'].map((k) => patternToNoteSequence(corners[k], 2, 16, qpm))
  );
  const zs = await model.encode(seqs); // Tensor2D [4, zdim]
  const arr = await zs.array();
  zs.dispose();
  return {
    A: new Float32Array(arr[0]),
    B: new Float32Array(arr[1]),
    C: new Float32Array(arr[2]),
    D: new Float32Array(arr[3]),
  };
}

// 패드 좌표(x,y)에서 잠재공간 보간 -> 디코드 -> 16스텝 패턴
export async function decodeAtPosition(encodedCorners, x, y, temperature = 0.8) {
  const wA = (1 - x) * (1 - y),
        wB = x * (1 - y),
        wC = (1 - x) * y,
        wD = x * y;

  const zdim = encodedCorners.A.length;
  const z = new Float32Array(zdim);
  for (let i = 0; i < zdim; i++) {
    z[i] =
      wA * encodedCorners.A[i] +
      wB * encodedCorners.B[i] +
      wC * encodedCorners.C[i] +
      wD * encodedCorners.D[i];
  }

  const model = await loadDrumsVAE();
  const zTensor = tf.tensor2d([Array.from(z)]); // [1, zdim]
  const outSeqs = await model.decode(zTensor, temperature);
  zTensor.dispose();
  const seq = outSeqs[0];
  return noteSequenceToPattern(seq, 16);
}
