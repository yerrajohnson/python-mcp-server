import HubIcon from '@mui/icons-material/Hub';
import {
  AppBar,
  Box,
  Container,
  IconButton,
  Tab,
  Tabs,
  Toolbar,
  Typography,
} from '@mui/material';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import './index.css';
import { AppProviders, McpServersPage, SpecsPage } from './frontend_core';

function AppShell({ dark, onToggleTheme }: { dark: boolean; onToggleTheme: () => void }) {
  const location = useLocation();
  const tab = location.pathname.startsWith('/mcp') ? 1 : 0;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} color="transparent" sx={{ borderBottom: 1, borderColor: 'divider', backdropFilter: 'blur(8px)' }}>
        <Toolbar>
          <HubIcon color="primary" sx={{ mr: 1 }} />
          <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 700 }}>
            OpenAPI → MCP Generator
          </Typography>
          <IconButton onClick={onToggleTheme} color="inherit">
            {dark ? <LightModeIcon /> : <DarkModeIcon />}
          </IconButton>
        </Toolbar>
        <Container maxWidth="xl">
          <Tabs value={tab}>
            <Tab label="OpenAPI Specifications" component={Link} to="/specs" />
            <Tab label="MCP Servers" component={Link} to="/mcp" />
          </Tabs>
        </Container>
      </AppBar>
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Routes>
          <Route path="/" element={<Navigate to="/specs" replace />} />
          <Route path="/specs" element={<SpecsPage />} />
          <Route path="/mcp" element={<McpServersPage />} />
        </Routes>
      </Container>
    </Box>
  );
}

export default function App() {
  const [dark, setDark] = useState(false);

  return (
    <AppProviders dark={dark}>
      <BrowserRouter>
        <AppShell dark={dark} onToggleTheme={() => setDark((d) => !d)} />
      </BrowserRouter>
    </AppProviders>
  );
}

const rootElement = document.getElementById('root');
if (rootElement) {
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
