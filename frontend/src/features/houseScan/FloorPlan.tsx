import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { projectRoom, type PlanLine } from './geometry';
import type { HouseRoom } from './types';

type Props = { room: HouseRoom; selectedWallId: string | null; onSelectWall: (id: string) => void };

/** Top-down projection of captured geometry. Quote overrides never warp the scan. */
export default function FloorPlan({ room, selectedWallId, onSelectWall }: Props) {
  const { colors } = useTheme();
  const [width, setWidth] = useState(0);
  const height = Math.min(420, Math.max(280, width * 0.72));
  const plan = useMemo(() => projectRoom(room, width, height), [room, width, height]);

  const lineStyle = (line: PlanLine, thickness: number) => {
    const dx = line.end.x - line.start.x;
    const dy = line.end.y - line.start.y;
    const length = Math.hypot(dx, dy);
    return {
      position: 'absolute' as const,
      left: (line.start.x + line.end.x) / 2 - length / 2,
      top: (line.start.y + line.end.y) / 2 - thickness / 2,
      width: length, height: thickness,
      transform: [{ rotate: `${Math.atan2(dy, dx) * 180 / Math.PI}deg` }],
    };
  };

  return <View>
    <View testID="house-floor-plan" onLayout={event => setWidth(event.nativeEvent.layout.width)}
      style={[styles.canvas, { height, backgroundColor: colors.backgroundSecondary, borderColor: colors.border }]}>
      {plan.walls.map(line => <Pressable key={line.id}
        testID={`house-plan-wall-${line.id}`}
        accessibilityRole="button" accessibilityLabel={`Parete ${line.index + 1}, mostra misura`}
        accessibilityState={{ selected: selectedWallId === line.id }}
        onPress={() => onSelectWall(line.id)}
        style={lineStyle(line, tokens.touch.min)}>
        <View style={{ marginTop: 20, height: 4, borderRadius: 2, backgroundColor: selectedWallId === line.id ? colors.accent : colors.textSecondary }} />
      </Pressable>)}
      {plan.doors.map(line => <View pointerEvents="none" key={`door-${line.id}`} style={[lineStyle(line, 7), { backgroundColor: colors.surface, borderColor: colors.borderStrong, borderWidth: 1 }]} />)}
      {plan.windows.map(line => <View pointerEvents="none" key={`window-${line.id}`} style={[lineStyle(line, 5), { backgroundColor: colors.info }]} />)}
      {plan.walls.map(line => <Pressable key={`label-${line.id}`}
        accessibilityRole="button" accessibilityLabel={`Seleziona parete ${line.index + 1}`}
        onPress={() => onSelectWall(line.id)}
        style={[styles.numberTap, {
          left: (line.start.x + line.end.x) / 2 - 22,
          top: (line.start.y + line.end.y) / 2 - 22,
        }]}>
        <View style={[styles.number, { borderColor: selectedWallId === line.id ? colors.accent : colors.borderStrong, backgroundColor: selectedWallId === line.id ? colors.accent : colors.surface }]}>
          <Text style={[styles.numberText, { color: selectedWallId === line.id ? colors.onAccent : colors.textPrimary }]}>{line.index + 1}</Text>
        </View>
      </Pressable>)}
      {!plan.walls.length && width > 0 && <Text style={[styles.noGeometry, { color: colors.textSecondary }]}>La pianta di questa stanza non è visualizzabile.</Text>}
    </View>
    <View style={styles.legend}>
      <Text style={[styles.legendText, { color: colors.textSecondary }]}>Vista dall’alto · tocca una parete</Text>
      <Text style={[styles.legendText, { color: colors.textTertiary }]}>Porte in chiaro · finestre azzurre</Text>
    </View>
  </View>;
}

const styles = StyleSheet.create({
  canvas: { borderWidth: 1, borderRadius: tokens.radius.lg, overflow: 'hidden' },
  numberTap: { position: 'absolute', width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  number: { width: 25, height: 25, borderRadius: 13, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  numberText: { ...tokens.typography.caption, fontWeight: '600' },
  noGeometry: { ...tokens.typography.bodySmall, textAlign: 'center', margin: 40 },
  legend: { gap: 3, paddingTop: tokens.spacing.sm },
  legendText: { ...tokens.typography.caption },
});
