// src/components/beat/BlendPad.jsx
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Typography, FormControl, Select, MenuItem, Stack, Switch, FormControlLabel, CircularProgress } from '@mui/material';
import { PRESETS, clonePattern } from './presets';
import { loadDrumsVAE, encodeCorners, decodeAtPosition } from '../../lib/drumsVAE';

// 단순(기존) 블렌딩용 가중치
const weights = (x, y) => ({
  A: (1 - x) * (1 - y),
  B: x * (1 - y),
  C: (1 - x) * y,
  D: x * y,
});

// (폴백) 패턴 레벨 이중선형 블렌딩
function blendPatterns(corners, x, y, thresh = 0.5) {
  const w = weights(x, y);
  const tracks = ['kick', 'snare', 'hat'];
  const out = {};
  tracks.forEach((t) => {
    out[t] = Array.from({ length: 16 }, (_, i) => {
      const v =
        w.A * (corners.A[t][i] ? 1 : 0) +
        w.B * (corners.B[t][i] ? 1 : 0) +
        w.C * (corners.C[t][i] ? 1 : 0) +
        w.D * (corners.D[t][i] ? 1 : 0);
      return v >= thresh;
    });
  });
  return out;
}

// 디코드 호출 폭주 방지를 위한 간단 디바운서
function useDebouncedCallback(fn, delay = 120) {
  const tRef = useRef(null);
  return (...args) => {
    if (tRef.current) clearTimeout(tRef.current);
    tRef.current = setTimeout(() => fn(...args), delay);
  };
}

export default function BlendPad({ colors, corners, onChangeCorners, onBlend }) {
  const padRef = useRef(null);
  const [pos, setPos] = useState({ x: 0.2, y: 0.3 });
  const [dragging, setDragging] = useState(false);

  const [sel, setSel] = useState({ A: '', B: '', C: '', D: '' }); // preset Select 표시용
  const presetNames = useMemo(() => Object.keys(PRESETS), []);

  // 🔥 ML 보간 사용 여부 + 모델/코너 인코딩 상태
  const [useML, setUseML] = useState(true);
  const [modelReady, setModelReady] = useState(false);
  const [encoded, setEncoded] = useState(null); // {A,B,C,D} Float32Array
  const [decoding, setDecoding] = useState(false);

  // 모델 로딩
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        await loadDrumsVAE();
        if (mounted) setModelReady(true);
      } catch (e) {
        console.warn('[BlendPad] VAE load failed, fallback to simple blend.', e);
        if (mounted) {
          setModelReady(false);
          setUseML(false);
        }
      }
    })();
    return () => { mounted = false; };
  }, []);

  // 코너가 바뀌면 잠재벡터 다시 인코딩
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!useML || !modelReady) return;
      try {
        const enc = await encodeCorners(corners);
        if (!cancelled) setEncoded(enc);
      } catch (e) {
        console.warn('[BlendPad] encode failed, fallback to simple blend.', e);
        if (!cancelled) {
          setEncoded(null);
          setUseML(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [corners, useML, modelReady]);

  const getXY = (clientX, clientY) => {
    const el = padRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (clientX - r.left) / r.width));
    const y = Math.min(1, Math.max(0, (clientY - r.top) / r.height));
    return { x, y };
  };

  // ML decode (디바운스)
  const debouncedDecode = useDebouncedCallback(async (p) => {
    if (!useML || !modelReady || !encoded) return;
    setDecoding(true);
    try {
      const pat = await decodeAtPosition(encoded, p.x, p.y, 0.85);
      onBlend(pat);
    } catch (e) {
      console.warn('[BlendPad] decode failed, fallback to simple blend.', e);
      onBlend(blendPatterns(corners, p.x, p.y));
    } finally {
      setDecoding(false);
    }
  }, 120);

  const startDrag = (e) => {
    const p = getXY(e.clientX, e.clientY);
    if (!p) return;
    setDragging(true);
    setPos(p);
    if (useML && modelReady && encoded) debouncedDecode(p);
    else onBlend(blendPatterns(corners, p.x, p.y));
  };

  // 전역 리스너(정리 철저)
  useEffect(() => {
    const onMove = (e) => {
      if (!dragging) return;
      const p = getXY(e.clientX, e.clientY);
      if (!p) return;
      setPos(p);
      if (useML && modelReady && encoded) debouncedDecode(p);
      else onBlend(blendPatterns(corners, p.x, p.y));
    };
    const onUp = () => setDragging(false);

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [dragging, useML, modelReady, encoded, corners, onBlend, debouncedDecode]);

  // 언마운트 시 드래그 해제
  useEffect(() => () => setDragging(false), []);

  const handlePreset = (key, name) => {
    if (!name) return;
    const next = {
      A: clonePattern(corners.A),
      B: clonePattern(corners.B),
      C: clonePattern(corners.C),
      D: clonePattern(corners.D),
    };
    next[key] = clonePattern(PRESETS[name]);
    onChangeCorners(next);
    setSel((s) => ({ ...s, [key]: '' })); // placeholder 유지

    // 코너 교체 즉시 현재 위치로 갱신
    const p = pos;
    if (useML && modelReady && encoded) {
      // 새 코너로 재인코딩이 끝나야 정확하지만, 일단 즉시 폴백 결과를 보여주고,
      // 인코딩 완료되면 다음 드래그/이동에서 ML이 반영됩니다.
      onBlend(blendPatterns(next, p.x, p.y));
    } else {
      onBlend(blendPatterns(next, p.x, p.y));
    }
  };

  return (
    <Stack spacing={2}>
      {/* 상단 토글: AI 보간 */}
      <FormControlLabel
        control={<Switch checked={useML && modelReady} onChange={(e)=>setUseML(e.target.checked)} />}
        label={
          modelReady ? 'AI 보간 사용' : (
            <Box sx={{ display:'inline-flex', alignItems:'center', gap:1 }}>
              <span>AI 보간 준비 중</span>
              <CircularProgress size={14} />
            </Box>
          )
        }
        sx={{ color: colors.textLight }}
      />

      {/* 2D 패드 */}
      <Box
        ref={padRef}
        onMouseDown={startDrag}
        sx={{
          position: 'relative',
          width: '100%', aspectRatio: '1 / 1',
          borderRadius: 2, border: `1px solid ${colors.border}`,
          background: `linear-gradient(45deg, #222, #2a2a2a)`,
          overflow: 'hidden', userSelect: 'none', cursor: 'pointer'
        }}
        title="드래그해서 블렌딩"
      >
        {/* 그리드 */}
        <Box sx={{
          position: 'absolute', inset: 0,
          backgroundImage:
            'linear-gradient(#0000 95%, rgba(255,255,255,0.04) 95%),' +
            'linear-gradient(90deg, #0000 95%, rgba(255,255,255,0.04) 95%)',
          backgroundSize: '20px 20px', pointerEvents: 'none'
        }} />

        {/* 모서리 라벨 */}
        <CornerLabel pos="topLeft" label="A" colors={colors} />
        <CornerLabel pos="topRight" label="B" colors={colors} />
        <CornerLabel pos="bottomLeft" label="C" colors={colors} />
        <CornerLabel pos="bottomRight" label="D" colors={colors} />

        {/* puck */}
        <Box sx={{
          position: 'absolute', width: 18, height: 18,
          borderRadius: '50%', border: '2px solid white', background: colors.accent,
          left: `calc(${pos.x * 100}% - 9px)`, top: `calc(${pos.y * 100}% - 9px)`,
          boxShadow: `0 0 20px ${colors.shadow}`, pointerEvents: 'none'
        }} />

        {/* 디코딩 상태 표시 */}
        {decoding && (
          <Box sx={{
            position:'absolute', right:8, bottom:8,
            fontSize:12, color: colors.textLight, bgcolor:'rgba(0,0,0,.35)',
            border:`1px solid ${colors.border}`, borderRadius:1, px:1, py:.25
          }}>
            AI 보간 중...
          </Box>
        )}
      </Box>

      {/* 모서리 프리셋 선택 */}
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
        {(['A','B','C','D']).map((k) => (
          <FormControl key={k} size="small" sx={{ bgcolor:'#111', borderRadius: 1 }}>
            <Typography sx={{ color: colors.textLight, fontSize: 12, mb: .5, mx: .5 }}>
              Corner {k}
            </Typography>
            <Select
              value={sel[k]}
              displayEmpty
              renderValue={() => 'Preset 선택'}
              onChange={(e)=> handlePreset(k, e.target.value)}
              sx={{ color:'#fff', '& .MuiOutlinedInput-notchedOutline': { borderColor: colors.border } }}
            >
              {presetNames.map((name) => (
                <MenuItem key={name} value={name}>{name}</MenuItem>
              ))}
            </Select>
          </FormControl>
        ))}
      </Box>
    </Stack>
  );
}

function CornerLabel({ pos, label, colors }) {
  const style = {
    position: 'absolute', color: colors.textLight, fontSize: 12,
    px: .75, py: .25, borderRadius: 1, bgcolor: 'rgba(0,0,0,.35)', border: `1px solid ${colors.border}`
  };
  const map = {
    topLeft: { left: 8, top: 6 },
    topRight: { right: 8, top: 6 },
    bottomLeft: { left: 8, bottom: 6 },
    bottomRight: { right: 8, bottom: 6 },
  };
  return <Box sx={{ ...style, ...map[pos] }}>{label}</Box>;
}
