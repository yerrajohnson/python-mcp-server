import DeleteIcon from '@mui/icons-material/Delete';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import VisibilityIcon from '@mui/icons-material/Visibility';
import {
  CircularProgress,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  useDeleteSpec,
  useGenerateMetadata,
  useParseSpec,
  useSpecifications,
} from '../../hooks/useSpecs';
import type { SpecificationSummary } from '../../types';
import { StatusChip } from '../common/StatusChip';

interface Props {
  onView: (spec: SpecificationSummary) => void;
}

export function SpecsTable({ onView }: Props) {
  const { data, isLoading, error } = useSpecifications();
  const del = useDeleteSpec();
  const parse = useParseSpec();
  const meta = useGenerateMetadata();

  if (isLoading) {
    return (
      <Paper sx={{ p: 4, textAlign: 'center' }}>
        <CircularProgress />
      </Paper>
    );
  }

  if (error) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography color="error">{(error as Error).message}</Typography>
      </Paper>
    );
  }

  if (!data?.length) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography color="text.secondary">No specifications uploaded yet.</Typography>
      </Paper>
    );
  }

  return (
    <TableContainer component={Paper}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Spec Name</TableCell>
            <TableCell>Version</TableCell>
            <TableCell>File Type</TableCell>
            <TableCell>Upload Date</TableCell>
            <TableCell>Status</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((spec) => {
            const busy =
              (parse.isPending && parse.variables === spec.id) ||
              (meta.isPending && meta.variables === spec.id) ||
              (del.isPending && del.variables === spec.id);
            return (
              <TableRow key={spec.id} hover>
                <TableCell>
                  <Typography sx={{ fontWeight: 600 }}>{spec.name}</Typography>
                  {spec.error_message && (
                    <Typography variant="caption" color="error" sx={{ display: 'block' }}>
                      {spec.error_message}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>{spec.version}</TableCell>
                <TableCell sx={{ textTransform: 'uppercase' }}>{spec.file_type}</TableCell>
                <TableCell>{new Date(spec.upload_date).toLocaleString()}</TableCell>
                <TableCell>
                  <StatusChip status={spec.status} />
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="View">
                    <IconButton size="small" onClick={() => onView(spec)} disabled={busy}>
                      <VisibilityIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Parse">
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={() => parse.mutate(spec.id)}
                      disabled={busy}
                    >
                      {parse.isPending && parse.variables === spec.id ? (
                        <CircularProgress size={16} />
                      ) : (
                        <PlayArrowIcon fontSize="small" />
                      )}
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Generate Metadata">
                    <IconButton
                      size="small"
                      color="secondary"
                      onClick={() => meta.mutate(spec.id)}
                      disabled={busy || spec.status === 'uploaded'}
                    >
                      {meta.isPending && meta.variables === spec.id ? (
                        <CircularProgress size={16} />
                      ) : (
                        <AutoFixHighIcon fontSize="small" />
                      )}
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Delete">
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => {
                        if (confirm(`Delete "${spec.name}"?`)) del.mutate(spec.id);
                      }}
                      disabled={busy}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
