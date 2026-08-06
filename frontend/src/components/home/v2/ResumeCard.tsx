import { View, Text, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { tokens } from '@/src/theme/tokens';
import { HomeItem } from '@/src/api/client';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { navigateHomeAction } from './homeNav';

export function ResumeCard({ item, onResume }: { item: HomeItem; onResume?: () => void }) {
  const router = useRouter();
  if (!item) return null;
  const action = item.actions?.find((a) => a.kind === 'resume') || item.actions?.[0];

  return (
    <View style={styles.card} testID="resume-card">
      <Text style={styles.h} accessibilityRole="header">Continua da dove avevi lasciato</Text>
      <Text style={styles.title}>{item.title}</Text>
      {item.description ? <Text style={styles.desc}>{item.description}</Text> : null}
      <ActionBtn
        primary
        label={action?.label || 'Continua'}
        icon="play"
        testID="btn-resume"
        // Never "Apri chat" — Continua only
        onPress={async () => {
          if (action) await navigateHomeAction(router, action, item);
          onResume?.();
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: 8,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  h: { fontSize: 16, fontWeight: '600', color: tokens.color.onSurface },
  title: { fontSize: 15, fontWeight: '600', color: tokens.color.onSurface },
  desc: { fontSize: 13, color: tokens.color.onSurfaceMuted, lineHeight: 18 },
});
