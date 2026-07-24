import { Chip } from '@mui/material';
import type { SpecStatus } from '../../types';

const colorMap: Record<
  SpecStatus,
  'default' | 'info' | 'success' | 'warning' | 'error' | 'primary' | 'secondary'
> = {
  uploaded: 'default',
  parsing: 'info',
  parsed: 'success',
  parse_error: 'error',
  generating: 'warning',
  generated: 'primary',
  error: 'error',
};

export function StatusChip({ status }: { status: SpecStatus }) {
  return (
    <Chip
      size="small"
      label={status.replace('_', ' ')}
      color={colorMap[status]}
      sx={{ textTransform: 'capitalize' }}
    />
  );
}
