// ScoreToMusic.js - MIDI 파일 직접 재생 버전

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMusicContext } from '../context/MusicContext';
import {
    Container,
    Typography,
    Button,
    CircularProgress,
    Box,
    Paper,
} from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';

const ScoreToMusic = () => {
    const [pdfFile, setPdfFile] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [fileName, setFileName] = useState('');
    const navigate = useNavigate();
    
    const { actions } = useMusicContext();

    const handleFileChange = (event) => {
        const file = event.target.files[0];
        if (file && file.type === "application/pdf") {
            setPdfFile(file);
            setFileName(file.name);
        } else {
            alert("PDF 파일만 업로드할 수 있습니다.");
            setPdfFile(null);
            setFileName('');
        }
    };

    const handleSubmit = async () => {
        if (!pdfFile) {
            alert("악보 PDF 파일을 업로드해주세요.");
            return;
        }

        setIsLoading(true);
        const formData = new FormData();
        formData.append('score', pdfFile);

        try {
            // 악보 처리 요청 (MIDI 생성)
            const response = await fetch('http://127.0.0.1:5000/api/process-score', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || '악보 처리에 실패했습니다.');
            }

            const data = await response.json();
            console.log('Server response:', data);

            if (!data.success || !data.result) {
                throw new Error('MIDI 파일 생성에 실패했습니다.');
            }

            // Result에 MIDI 음악 데이터 저장
            actions.setResult?.({
                convertedMusic: {
                    id: data.result.id,
                    title: data.result.title,
                    audioUrl: data.result.audioUrl,
                    genres: data.result.genres || ['Classical'],
                    moods: data.result.moods || [],
                    duration: data.result.duration || 180,
                    createdAt: data.result.createdAt || new Date().toISOString(),
                    type: 'score-midi',
                    originalFile: fileName,
                    targetGenre: 'Classical'
                }
            });

            console.log('Music data set successfully');

            // 결과 페이지로 이동
            navigate('/result');

        } catch (error) {
            console.error("Error processing score:", error);
            alert(`악보 처리 중 오류가 발생했습니다: ${error.message}`);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <Container maxWidth="md" sx={{ mt: 4 }}>
            <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
                <Typography variant="h4" gutterBottom>
                    악보 연주하기 🎼
                </Typography>
                <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
                    PDF 악보 파일을 업로드하면 AI가 분석하여 MIDI로 연주해줍니다.
                </Typography>

                <Box
                    sx={{
                        border: '2px dashed grey',
                        borderRadius: '10px',
                        p: 4,
                        mb: 3,
                        cursor: 'pointer',
                        transition: 'all 0.3s',
                        '&:hover': {
                            borderColor: 'primary.main',
                            bgcolor: 'action.hover'
                        }
                    }}
                    onClick={() => document.getElementById('pdf-upload').click()}
                >
                    <UploadFileIcon sx={{ fontSize: 60, color: 'grey.500' }} />
                    <Typography>
                        {fileName || '클릭하여 PDF 파일을 선택하세요'}
                    </Typography>
                    <input
                        type="file"
                        id="pdf-upload"
                        hidden
                        accept="application/pdf"
                        onChange={handleFileChange}
                    />
                </Box>

                <Button
                    variant="contained"
                    color="primary"
                    size="large"
                    onClick={handleSubmit}
                    disabled={isLoading || !pdfFile}
                    sx={{ minWidth: '200px', minHeight: '50px' }}
                >
                    {isLoading ? <CircularProgress size={24} /> : 'MIDI 생성 및 연주'}
                </Button>

                {isLoading && (
                    <Box sx={{ mt: 3 }}>
                        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                            악보를 분석하고 MIDI 파일을 생성하는 중입니다...
                        </Typography>
                        <Typography variant="caption" sx={{ color: 'text.disabled', mt: 1, display: 'block' }}>
                            PDF → MusicXML → MIDI 변환 진행중 (약 1-2분 소요)
                        </Typography>
                    </Box>
                )}
            </Paper>
        </Container>
    );
};

export default ScoreToMusic;