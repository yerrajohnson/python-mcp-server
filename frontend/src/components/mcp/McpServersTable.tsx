import DownloadIcon from '@mui/icons-material/Download';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import VisibilityIcon from '@mui/icons-material/Visibility';
import {
  Chip,
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
import { mcpServersApi } from '../../api/client';
import { useMcpServerActions, useMcpServers } from '../../hooks/useSpecs';
import type { McpServerRecord } from '../../types';

interface Props {
  onView: (server: McpServerRecord) => void;
  onEdit: (server: McpServerRecord) => void;
}

export function McpServersTable({ onView, onEdit }: Props) {
  const { data = [], isLoading, error } = useMcpServers();
  const actions = useMcpServerActions();

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

  if (!data.length) {
    return (
      <Paper sx={{ p: 4, textAlign: 'center' }}>
        <Typography color="text.secondary">
          No MCP servers yet. Click <strong>Generate MCP Server</strong> to start the wizard.
        </Typography>
      </Paper>
    );
  }

  return (
    <TableContainer component={Paper}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>MCP Server Name</TableCell>
            <TableCell>Source Specification</TableCell>
            <TableCell>Tools</TableCell>
            <TableCell>Auth</TableCell>
            <TableCell>Server URL</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Created</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((server) => {
            const busy =
              (actions.start.isPending && actions.start.variables === server.id) ||
              (actions.stop.isPending && actions.stop.variables === server.id) ||
              (actions.remove.isPending && actions.remove.variables === server.id);
            return (
              <TableRow key={server.id} hover>
                <TableCell>
                  <Typography sx={{ fontWeight: 600 }}>{server.name}</Typography>
                </TableCell>
                <TableCell>{server.spec_name}</TableCell>
                <TableCell>{server.tool_count}</TableCell>
                <TableCell>{server.authentication.join(', ') || 'none'}</TableCell>
                <TableCell>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                    {server.server_url}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={server.status}
                    color={server.status === 'running' ? 'success' : 'default'}
                    sx={{ textTransform: 'capitalize' }}
                  />
                </TableCell>
                <TableCell>{new Date(server.created_date).toLocaleString()}</TableCell>
                <TableCell align="right">
                  <Tooltip title="View">
                    <IconButton size="small" onClick={() => onView(server)} disabled={busy}>
                      <VisibilityIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Edit">
                    <IconButton size="small" onClick={() => onEdit(server)} disabled={busy}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Download">
                    <IconButton
                      size="small"
                      onClick={() => window.open(mcpServersApi.downloadUrl(server.id), '_blank')}
                      disabled={busy}
                    >
                      <DownloadIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  {server.status === 'running' ? (
                    <Tooltip title="Stop">
                      <IconButton
                        size="small"
                        color="warning"
                        onClick={() => actions.stop.mutate(server.id)}
                        disabled={busy}
                      >
                        <StopIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  ) : (
                    <Tooltip title="Start">
                      <IconButton
                        size="small"
                        color="success"
                        onClick={() => actions.start.mutate(server.id)}
                        disabled={busy}
                      >
                        <PlayArrowIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                  <Tooltip title="Delete">
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => {
                        if (
                          confirm(
                            `Delete "${server.name}" and its ${server.tool_count} tool(s)? This cannot be undone.`,
                          )
                        )
                          actions.remove.mutate(server.id);
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
