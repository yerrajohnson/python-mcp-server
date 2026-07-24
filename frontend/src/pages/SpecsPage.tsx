import { Box, Stack, Typography } from '@mui/material';
import { useState } from 'react';
import { SpecUploadZone } from '../components/specs/SpecUploadZone';
import { SpecsTable } from '../components/specs/SpecsTable';
import { SpecViewerDialog } from '../components/specs/SpecViewerDialog';
import type { SpecificationSummary } from '../types';

export function SpecsPage() {
  const [viewId, setViewId] = useState<string | null>(null);

  const handleView = (spec: SpecificationSummary) => setViewId(spec.id);

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        OpenAPI Specifications
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Upload, validate, and parse OpenAPI specs to prepare MCP tool generation.
      </Typography>
      <Stack spacing={3}>
        <SpecUploadZone />
        <SpecsTable onView={handleView} />
      </Stack>
      <SpecViewerDialog specId={viewId} onClose={() => setViewId(null)} />
    </Box>
  );
}
