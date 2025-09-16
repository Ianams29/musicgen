// musicgen-app-main/src/pages/ScoreToMusic.js

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMusicContext } from '../context/MusicContext'; // 수정된 부분: useMusicContext 훅을 직접 import 합니다.
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
    
    // 수정된 부분: useMusicContext 훅을 호출하여 'actions'를 가져옵니다.
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
            const response = await fetch('http://127.0.0.1:5000/api/process-score', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || '음악 생성에 실패했습니다.');
            }

            const data = await response.json();
            
            // 수정된 부분: 기존 'completeGeneration' 액션을 사용하여 결과 상태를 업데이트합니다.
            actions.completeGeneration({
                musicUrl: data.musicUrl,
                prompt: `악보 '${fileName}' 기반으로 생성된 음악`
            });

            navigate('/result'); // 결과 페이지로 이동

        } catch (error) {
            console.error("Error generating music from score:", error);
            alert(`음악 생성 중 오류가 발생했습니다: ${error.message}`);
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
                    PDF 악보 파일을 업로드하면 AI가 분석하여 음악을 연주해줍니다.
                </Typography>

                <Box
                    sx={{
                        border: '2px dashed grey',
                        borderRadius: '10px',
                        p: 4,
                        mb: 3,
                        cursor: 'pointer'
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
                    {isLoading ? <CircularProgress size={24} /> : '음악 생성'}
                </Button>
            </Paper>
        </Container>
    );
};

export default ScoreToMusic;