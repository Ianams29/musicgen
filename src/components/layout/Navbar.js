// src/components/layout/Navbar.js
import React from 'react';
import { 
  AppBar, 
  Toolbar, 
  Typography, 
  Button, 
  Box,
  Container,
  IconButton
} from '@mui/material';
// 사용하지 않는 아이콘들을 모두 제거했습니다.
import { Menu } from '@mui/icons-material';
// 사용하지 않는 useLocation을 제거했습니다.
import { useNavigate } from 'react-router-dom';
import { NavLink } from 'react-router-dom';
// 검은색 배경에 에메랄드 테마
const colors = {
  background: '#0A0A0A',         // 검은색 배경
  cardBg: '#1A1A1A',            // 어두운 카드 배경
  primary: '#50E3C2',           // 에메랄드 (Emerald)
  secondary: '#40D9B8',         // 연한 에메랄드
  accent: '#2DD4BF',            // 터콰이즈 (Teal)
  text: '#FFFFFF',              // 흰색 텍스트
  textLight: '#CCCCCC',         // 연한 회색 텍스트
  border: '#333333',            // 어두운 테두리
  shadow: 'rgba(80, 227, 194, 0.3)' // 에메랄드 그림자
};

const Navbar = () => {
  const navigate = useNavigate();

  const handleNavigation = (path) => {
    navigate(path);
  };

  return (
    <AppBar 
      position="sticky" 
      elevation={0}
      sx={{
        bgcolor: colors.cardBg,
        borderBottom: `1px solid ${colors.accent}`,
      }}
    >
      <Container maxWidth="xl">
        <Toolbar 
          disableGutters
          sx={{
            minHeight: { xs: '64px', md: '80px' },
            justifyContent: 'space-between'
          }}
        >
          {/* 로고 섹션 */}
          <Box 
            sx={{ 
              display: 'flex', 
              alignItems: 'center',
              cursor: 'pointer'
            }}
            onClick={() => handleNavigation('/')}
          >
            <Typography
              variant="h6"
              component="div"
              sx={{
                fontWeight: 600,
                color: colors.text,
                fontSize: { xs: '1.2rem', md: '1.5rem' }
              }}
            >
              AI Music Studio
            </Typography>
          </Box>

          {/* 네비게이션 메뉴 */}
          <Box sx={{ display: { xs: 'none', md: 'flex' }, gap: 1 }}>
            <Button
              onClick={() => handleNavigation('/generate')}
              sx={{
                color: colors.text,
                fontWeight: 500,
                textTransform: 'none',
                px: 3,
                py: 1,
                borderRadius: 2,
                '&:hover': {
                  bgcolor: colors.background,
                  color: colors.accent
                }
              }}
            >
              음악 생성
            </Button>
            
            <Button
              onClick={() => handleNavigation('/convert')}
              sx={{
                color: colors.text,
                fontWeight: 500,
                textTransform: 'none',
                px: 3,
                py: 1,
                borderRadius: 2,
                '&:hover': {
                  bgcolor: colors.background,
                  color: colors.accent
                }
              }}
            >
              비트 만들기
            </Button>
            
            <Button color="inherit" component={NavLink} to="/score-to-music">
              악보 연주
            </Button>

            <Button
              onClick={() => handleNavigation('/library')}
              sx={{
                color: colors.text,
                fontWeight: 500,
                textTransform: 'none',
                px: 3,
                py: 1,
                borderRadius: 2,
                '&:hover': {
                  bgcolor: colors.background,
                  color: colors.accent
                }
              }}
            >
              라이브러리
            </Button>
          </Box>

          {/* 모바일 메뉴 버튼 */}
          <Box sx={{ display: { xs: 'flex', md: 'none' } }}>
            <IconButton
              size="large"
              sx={{
                color: colors.text,
                '&:hover': {
                  bgcolor: colors.background,
                  color: colors.accent
                }
              }}
            >
              <Menu />
            </IconButton>
          </Box>
        </Toolbar>
      </Container>
    </AppBar>
  );
};

export default Navbar;