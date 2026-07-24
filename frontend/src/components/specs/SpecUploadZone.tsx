import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import { Alert, Box, Button, CircularProgress, Paper, Typography } from '@mui/material';
import { useCallback, useRef, useState } from 'react';
import { useUploadSpec } from '../../hooks/useSpecs';

const ACCEPT = '.yaml,.yml,.json';

export function SpecUploadZone() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const upload = useUploadSpec();

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      setLocalError(null);
      const file = files[0];
      if (!file) return;
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (!ext || !['yaml', 'yml', 'json'].includes(ext)) {
        setLocalError('Only YAML (.yaml, .yml) and JSON (.json) files are supported.');
        return;
      }
      try {
        await upload.mutateAsync(file);
      } catch (err) {
        setLocalError(err instanceof Error ? err.message : 'Upload failed');
      }
    },
    [upload],
  );

  return (
    <Paper
      variant="outlined"
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        void handleFiles(e.dataTransfer.files);
      }}
      sx={{
        p: 4,
        textAlign: 'center',
        borderStyle: 'dashed',
        borderWidth: 2,
        borderColor: dragOver ? 'primary.main' : 'divider',
        bgcolor: dragOver ? 'action.hover' : 'background.paper',
        transition: 'all 0.15s ease',
      }}
    >
      <CloudUploadIcon color="primary" sx={{ fontSize: 48, mb: 1 }} />
      <Typography variant="h6" gutterBottom>
        Upload OpenAPI Specification
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Drag & drop a YAML or JSON file, or click to browse
      </Typography>
      <Button
        variant="contained"
        startIcon={upload.isPending ? <CircularProgress size={16} color="inherit" /> : undefined}
        disabled={upload.isPending}
        onClick={() => inputRef.current?.click()}
      >
        {upload.isPending ? 'Uploading…' : 'Select File'}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          if (e.target.files) void handleFiles(e.target.files);
          e.target.value = '';
        }}
      />
      {(localError || upload.isError) && (
        <Box sx={{ mt: 2 }}>
          <Alert severity="error">{localError ?? (upload.error as Error)?.message}</Alert>
        </Box>
      )}
      {upload.isSuccess && !localError && (
        <Box sx={{ mt: 2 }}>
          <Alert severity="success">Uploaded successfully — click Parse to validate.</Alert>
        </Box>
      )}
    </Paper>
  );
}
