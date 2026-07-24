import {
  Checkbox,
  FormControlLabel,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  Typography,
} from '@mui/material';
import type { SpecificationSummary } from '../../types';

interface Props {
  specs: SpecificationSummary[];
  selected: Set<string>;
  onToggle: (id: string) => void;
}

export function SpecSelector({ specs, selected, onToggle }: Props) {
  const parsed = specs.filter((s) => s.status === 'parsed' || s.status === 'generated');

  return (
    <Paper sx={{ p: 2, height: '100%', overflow: 'auto' }}>
      <Typography variant="h6" gutterBottom>
        Uploaded Specifications
      </Typography>
      {!parsed.length && (
        <Typography color="text.secondary" variant="body2">
          Parse at least one specification in Tab 1 first.
        </Typography>
      )}
      <List dense>
        {parsed.map((spec) => (
          <ListItem key={spec.id} disablePadding>
            <ListItemButton onClick={() => onToggle(spec.id)} dense>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Checkbox edge="start" checked={selected.has(spec.id)} tabIndex={-1} disableRipple />
              </ListItemIcon>
              <ListItemText
                primary={spec.name}
                secondary={`${spec.endpoint_count} endpoints · v${spec.version}`}
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      {specs.some((s) => s.status === 'uploaded' || s.status === 'parse_error') && (
        <FormControlLabel
          disabled
          control={<Checkbox />}
          label={<Typography variant="caption">Unparsed specs are hidden</Typography>}
        />
      )}
    </Paper>
  );
}
