import { Box, Typography } from '@mui/material';

export function JsonViewer({ value, title }: { value: unknown; title?: string }) {
  const text = JSON.stringify(value ?? {}, null, 2);
  return (
    <Box sx={{ mb: 2 }}>
      {title && (
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          {title}
        </Typography>
      )}
      <Box
        component="pre"
        sx={{
          m: 0,
          p: 1.5,
          borderRadius: 1,
          bgcolor: 'action.hover',
          overflow: 'auto',
          maxHeight: 280,
          fontSize: 12,
          fontFamily: '"IBM Plex Mono", Consolas, monospace',
          lineHeight: 1.45,
        }}
      >
        {text}
      </Box>
    </Box>
  );
}
