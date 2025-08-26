// src/components/beat/TransportBar.jsx
import React, { useEffect, useMemo, useState } from 'react';
import { Box, Button, IconButton, Stack, TextField, Tooltip, Typography } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import DownloadIcon from '@mui/icons-material/Download';
import SendIcon from '@mui/icons-material/Send';

export default function TransportBar(props) {
  const {
    // 두 방식 모두 허용: value={{bpm,bars}} 또는 bpm={...} bars={...}
    value,
    bpm: bpmProp,
    bars: barsProp,

    onChangeBpm,
    onChangeBars,
    onPlay,
    onStop,
    onClear,
    onExport,
    onSendToGenerate,

    busy = false,
    busyMsg = '',
  } = props;

  // 안전 추출 (value가 undefined여도 동작)
  const initialBpm = useMemo(() => {
    if (typeof value?.bpm === 'number') return value.bpm;
    if (typeof bpmProp === 'number') return bpmProp;
    return 96;
  }, [value?.bpm, bpmProp]);

  const initialBars = useMemo(() => {
    if (typeof value?.bars === 'number') return value.bars;
    if (typeof barsProp === 'number') return barsProp;
    return 2;
  }, [value?.bars, barsProp]);

  const [bpmLocal, setBpmLocal] = useState(initialBpm);
  const [barsLocal, setBarsLocal] = useState(initialBars);

  // 외부 값이 바뀌면 동기화
  useEffect(() => setBpmLocal(initialBpm), [initialBpm]);
  useEffect(() => setBarsLocal(initialBars), [initialBars]);

  const handleBpmChange = (e) => {
    const v = Math.max(40, Math.min(240, Number(e.target.value) || 0));
    setBpmLocal(v);
    onChangeBpm?.(v);
  };

  const handleBarsChange = (e) => {
    const raw = Number(e.target.value) || 1;
    const v = Math.max(1, Math.min(16, raw));
    setBarsLocal(v);
    onChangeBars?.(v);
  };

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mr: 1 }}>
        <Tooltip title="재생">
          <span>
            <IconButton color="primary" onClick={onPlay} disabled={busy}>
              <PlayArrowIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="정지">
          <span>
            <IconButton onClick={onStop} disabled={busy}>
              <StopIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="초기화">
          <span>
            <IconButton onClick={onClear} disabled={busy}>
              <DeleteSweepIcon />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>

      <Stack direction="row" spacing={1} alignItems="center">
        <TextField
          label="BPM"
          type="number"
          size="small"
          value={bpmLocal}
          onChange={handleBpmChange}
          inputProps={{ min: 40, max: 240 }}
          sx={{ width: 110 }}
          disabled={busy}
        />
        <TextField
          label="마디"
          type="number"
          size="small"
          value={barsLocal}
          onChange={handleBarsChange}
          inputProps={{ min: 1, max: 16 }}
          sx={{ width: 110 }}
          disabled={busy}
        />
      </Stack>

      <Stack direction="row" spacing={1} sx={{ ml: 'auto' }}>
        <Button
          variant="outlined"
          startIcon={<DownloadIcon />}
          onClick={onExport}
          disabled={busy}
        >
          다운로드(WAV)
        </Button>
        <Button
          variant="contained"
          startIcon={<SendIcon />}
          onClick={onSendToGenerate}
          disabled={busy}
        >
          생성하기로 보내기
        </Button>
      </Stack>

      {busy ? (
        <Typography variant="body2" sx={{ ml: 2, opacity: 0.8 }}>
          {busyMsg || '처리 중...'}
        </Typography>
      ) : null}
    </Box>
  );
}
