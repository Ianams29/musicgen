import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';

// 컴포넌트 import
import Navbar from './components/layout/Navbar';
import MusicGeneration from './pages/MusicGeneration';
import MusicConversion from './pages/MusicConversion';
import ResultPage from './pages/ResultPage';
import Library from './pages/Library';
import { MusicContextProvider } from './context/MusicContext';

// Material-UI 테마 설정
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#6366F1', // 인디고
    },
    secondary: {
      main: '#8B5CF6', // 보라
    },
    success: {
      main: '#10B981', // 초록
    },
    warning: {
      main: '#F59E0B', // 주황
    },
    error: {
      main: '#EF4444', // 빨강
    },
    background: {
      default: '#F8FAFC', // 연한 회색
      paper: '#FFFFFF', // 흰색
    },
    text: {
      primary: '#1E293B', // 진한 회색
      secondary: '#64748B', // 중간 회색
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: {
      fontSize: '2.5rem',
      fontWeight: 700,
    },
    h2: {
      fontSize: '2rem',
      fontWeight: 600,
    },
    h3: {
      fontSize: '1.5rem',
      fontWeight: 500,
    },
    body1: {
      fontSize: '1rem',
      fontWeight: 400,
    },
    caption: {
      fontSize: '0.875rem',
      fontWeight: 400,
    },
  },
  shape: {
    borderRadius: 8,
  },
  spacing: 8,
});

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <MusicContextProvider>
        <Router>
          <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
            <Navbar />
            <Box component="main" sx={{ flexGrow: 1, bgcolor: 'background.default' }}>
              <Routes>
                <Route path="/" element={<MusicGeneration />} />
                <Route path="/generate" element={<MusicGeneration />} />
                <Route path="/convert" element={<MusicConversion />} />
                <Route path="/result" element={<ResultPage />} />
                <Route path="/library" element={<Library />} />
              </Routes>
            </Box>
          </Box>
        </Router>
      </MusicContextProvider>
    </ThemeProvider>
  );
}

export default App;
