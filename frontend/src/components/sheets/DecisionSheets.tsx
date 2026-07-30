import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, Pressable, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { Sheet, SheetSection } from '@/src/components/sheets/Sheet';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { DailySummary, DecisionExplanation, DecisionActionHistoryItem } from '@/src/api/client';
import {
  ruleLabel, CONFIDENCE_LABELS, RISK_LABELS, IMPACT_LABELS, USER_ACTION_LABELS,
  DAILY_SIGNAL_LABELS, ENERGY_LABELS, formatMinutes, formatDateTime, formatTime,
} from '@/src/utils/labels';
import { haptic } from '@/src/utils/haptic';

function riskColor(v?: string) {
  if (v === 'high') return tokens.color.error;
  if (v === 'medium') return tokens.color.warning;
  return tokens.color.success;
}
function riskBg(v?: string) {
  if (v === 'high') return tokens.color.errorBg;
  if (v === 'medium') return tokens.color.warningBg;
  return tokens.color.successBg;
}

function Stat({ label, value, color, bg }: any) {
  return (
    <View style={[s.statBox, bg ? { backgroundColor: bg } : null]}>
      <Text style={s.statLabel}>{label}</Text>
      <Text style={[s.statValue, color ? { color } : null]}>{value}</Text>
    </View>
  );
}

// ========== Why Now Sheet ==========
export function WhyNowSheet({ open, onClose, explanation }: {
  open: boolean; onClose: () => void; explanation: DecisionExplanation | null;
}) {
  if (!open) return null;
  if (!explanation) {
    return (
      <Sheet open={open} onClose={onClose} title="Perché adesso" testID="sheet-why">
        <View style={{ padding: 24 }}>
          <ActivityIndicator color={tokens.color.onSurfaceMuted} />
        </View>
      </Sheet>
    );
  }
  return (
    <Sheet open={open} onClose={onClose} title="Perché adesso" testID="sheet-why">
      <Text style={s.whyTitle}>{explanation.human_summary}</Text>

      <SheetSection title="Cosa la rende prioritaria">
        {explanation.applied_rules.map((r) => (
          <View key={r.id} style={s.ruleRow}>
            <View
              style={[
                s.ruleDot,
                {
                  backgroundColor:
                    r.weight === 'high' ? tokens.color.error :
                    r.weight === 'medium' ? tokens.color.warning :
                    tokens.color.info,
                },
              ]}
            />
            <View style={{ flex: 1 }}>
              <Text style={s.ruleLabel}>{ruleLabel(r.id)}</Text>
              {r.evidence?.map((e, i) => <Text key={i} style={s.ruleEvidence}>{e}</Text>)}
            </View>
          </View>
        ))}
        {explanation.applied_rules.length === 0 && <Text style={s.muted}>Nessuna regola applicata in modo particolare.</Text>}
      </SheetSection>

      <SheetSection title="Passi del ragionamento">
        {explanation.reasoning_steps.map((r, i) => <Text key={i} style={s.step}>• {r}</Text>)}
      </SheetSection>

      <SheetSection title="Stime">
        <View style={s.statRow}>
          <Stat label="Durata" value={formatMinutes(explanation.estimated_duration_minutes)} />
          <Stat label="Impatto" value={IMPACT_LABELS[explanation.estimated_impact]} />
        </View>
        <View style={s.statRow}>
          <Stat
            label="Rischio rinvio"
            value={RISK_LABELS[explanation.estimated_postpone_risk]}
            color={riskColor(explanation.estimated_postpone_risk)}
            bg={riskBg(explanation.estimated_postpone_risk)}
          />
          <Stat label="Confidenza" value={CONFIDENCE_LABELS[explanation.confidence]} />
        </View>
      </SheetSection>

      <SheetSection title="Dati utilizzati">
        {explanation.data_sources.map((d, i) => (
          <View key={i} style={s.sourceRow}>
            <Ionicons name="cube-outline" size={14} color={tokens.color.onSurfaceMuted} />
            <View style={{ flex: 1 }}>
              <Text style={s.sourceName}>{d.source}</Text>
              {d.notes && <Text style={s.sourceNotes}>{d.notes}</Text>}
              <Text style={s.sourceMeta}>
                Confidenza: {CONFIDENCE_LABELS[d.confidence] || d.confidence}
                {d.last_updated_at ? ` · aggiornato ${formatDateTime(d.last_updated_at)}` : ''}
              </Text>
            </View>
          </View>
        ))}
      </SheetSection>

      {explanation.context_used?.length > 0 && (
        <SheetSection title="Contesto considerato">
          {explanation.context_used.map((c, i) => <Text key={i} style={s.step}>• {c}</Text>)}
        </SheetSection>
      )}
    </Sheet>
  );
}

// ========== Daily Detail Sheet ==========
export function DailyDetailSheet({ open, onClose, daily }: {
  open: boolean; onClose: () => void; daily: DailySummary | null;
}) {
  if (!open || !daily) return null;
  return (
    <Sheet open={open} onClose={onClose} title="La tua giornata" testID="sheet-daily">
      <View style={s.statRow}>
        <Stat label="Score" value={`${daily.score}/100`} />
        <Stat label="Energia" value={ENERGY_LABELS[daily.energy_estimation.level]} />
      </View>
      <View style={s.statRow}>
        <Stat label="Eventi" value={String(daily.total_events)} />
        <Stat label="Confidenza" value={CONFIDENCE_LABELS[daily.confidence]} />
      </View>
      <SheetSection title="Impegni">
        {daily.busy_slots.length === 0 && <Text style={s.muted}>Nessun impegno pianificato.</Text>}
        {daily.busy_slots.map((b, i) => (
          <Text key={i} style={s.step}>
            • {formatTime(b.start)}–{formatTime(b.end)} · {formatMinutes(b.duration_min)}
            {b.category ? ` · ${b.category}` : ''}
          </Text>
        ))}
      </SheetSection>
      <SheetSection title="Finestre libere">
        {daily.free_slots.slice(0, 5).map((f, i) => (
          <Text key={i} style={s.step}>• {formatTime(f.start)}–{formatTime(f.end)} · {formatMinutes(f.duration_min)}</Text>
        ))}
      </SheetSection>
      {daily.signals.length > 0 && (
        <SheetSection title="Segnali">
          {daily.signals.map((sg) => <Text key={sg} style={s.step}>• {DAILY_SIGNAL_LABELS[sg] || sg}</Text>)}
        </SheetSection>
      )}
    </Sheet>
  );
}

// ========== Confirm Sheet ==========
export function ConfirmSheet({ open, onClose, title, body, confirmLabel, onConfirm, loading }: any) {
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title={title} testID="sheet-confirm">
      <Text style={s.step}>{body}</Text>
      <View style={s.actions}>
        <ActionBtn label="Annulla" icon="close" onPress={onClose} />
        <ActionBtn primary label={confirmLabel} icon="checkmark" onPress={onConfirm} loading={loading} testID="btn-confirm" />
      </View>
    </Sheet>
  );
}

// ========== Partial Sheet ==========
export function PartialSheet({ open, onClose, onSubmit, loading }: {
  open: boolean; onClose: () => void; onSubmit: (pct: number, note?: string) => void; loading?: boolean;
}) {
  const [pct, setPct] = useState(50);
  const [note, setNote] = useState('');
  useEffect(() => { if (open) { setPct(50); setNote(''); } }, [open]);
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title="Progresso parziale" testID="sheet-partial">
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
        {[25, 50, 75].map((p) => (
          <Pressable
            key={p}
            onPress={() => { haptic('select'); setPct(p); }}
            style={({ pressed }) => [s.pctBtn, pct === p && s.pctBtnActive, pressed && s.pressed]}
            accessibilityRole="button"
            accessibilityLabel={`${p} percento`}
            accessibilityState={{ selected: pct === p }}
          >
            <Text style={[s.pctBtnText, pct === p && s.pctBtnTextActive]}>{p}%</Text>
          </Pressable>
        ))}
      </View>
      <TextInput
        placeholder="Nota (opzionale)" placeholderTextColor={tokens.color.onSurfaceMuted}
        value={note} onChangeText={setNote} style={s.input}
        accessibilityLabel="Nota facoltativa"
      />
      <View style={s.actions}>
        <ActionBtn label="Annulla" icon="close" onPress={onClose} />
        <ActionBtn primary label="Salva" icon="save-outline" onPress={() => onSubmit(pct, note || undefined)} loading={loading} />
      </View>
    </Sheet>
  );
}

// ========== Postpone Sheet ==========
export function PostponeSheet({ open, onClose, onSubmit, loading }: {
  open: boolean; onClose: () => void; onSubmit: (until: string, reason?: string) => void; loading?: boolean;
}) {
  const [reason, setReason] = useState('');
  useEffect(() => { if (open) setReason(''); }, [open]);
  const now = new Date();
  const options = [
    { label: 'Più tardi oggi', dt: new Date(now.getTime() + 3 * 3600 * 1000) },
    { label: 'Domani', dt: new Date(now.getTime() + 24 * 3600 * 1000) },
    {
      label: 'Weekend',
      dt: (() => {
        const d = new Date(now);
        const day = d.getDay();
        const offset = (6 - day + 7) % 7 || 7;
        d.setDate(d.getDate() + offset);
        return d;
      })(),
    },
  ];
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title="Rimanda" testID="sheet-postpone">
      {options.map((o) => (
        <Pressable
          key={o.label}
          onPress={() => onSubmit(o.dt.toISOString(), reason || undefined)}
          style={({ pressed }) => [s.optionBtn, pressed && s.pressed]}
          disabled={loading}
          accessibilityRole="button"
          accessibilityLabel={`Rimanda a ${o.label}`}
        >
          <Ionicons name="hourglass-outline" size={14} color={tokens.color.onSurface} />
          <Text style={s.optionText}>{o.label}</Text>
          <Text style={s.optionMeta}>{formatDateTime(o.dt.toISOString())}</Text>
        </Pressable>
      ))}
      <TextInput
        placeholder="Motivo (opzionale)" placeholderTextColor={tokens.color.onSurfaceMuted}
        value={reason} onChangeText={setReason} style={s.input}
        accessibilityLabel="Motivo facoltativo"
      />
      <View style={s.actions}>
        <ActionBtn label="Annulla" icon="close" onPress={onClose} />
      </View>
    </Sheet>
  );
}

// ========== Reason Sheet (blocca / ignora) ==========
export function ReasonSheet({ open, onClose, title, placeholder, required, onSubmit, loading }: any) {
  const [text, setText] = useState('');
  useEffect(() => { if (open) setText(''); }, [open]);
  const canSubmit = !required || text.trim().length > 0;
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title={title} testID="sheet-reason">
      <TextInput
        placeholder={placeholder} placeholderTextColor={tokens.color.onSurfaceMuted}
        value={text} onChangeText={setText}
        style={[s.input, { minHeight: 88 }]}
        multiline
        accessibilityLabel={placeholder}
      />
      <View style={s.actions}>
        <ActionBtn label="Annulla" icon="close" onPress={onClose} />
        <ActionBtn
          primary label="Conferma" icon="checkmark"
          onPress={() => canSubmit && onSubmit(text.trim() || undefined)}
          loading={loading}
        />
      </View>
    </Sheet>
  );
}

// ========== More Menu ==========
export function MoreMenu({ open, onClose, onBlock, onDismiss, onHistory }: {
  open: boolean; onClose: () => void; onBlock: () => void; onDismiss: () => void; onHistory: () => void;
}) {
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title="Altre azioni" testID="sheet-more">
      <Pressable style={({ pressed }) => [s.optionBtn, pressed && s.pressed]} onPress={onHistory}
        accessibilityRole="button" accessibilityLabel="Vedi cronologia">
        <Ionicons name="time-outline" size={16} color={tokens.color.onSurface} />
        <Text style={s.optionText}>Cronologia</Text>
        <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurfaceMuted} />
      </Pressable>
      <Pressable style={({ pressed }) => [s.optionBtn, pressed && s.pressed]} onPress={onBlock}
        accessibilityRole="button" accessibilityLabel="Blocca la decision">
        <Ionicons name="lock-closed-outline" size={16} color={tokens.color.warning} />
        <Text style={[s.optionText, { color: tokens.color.warning }]}>Blocca</Text>
        <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurfaceMuted} />
      </Pressable>
      <Pressable style={({ pressed }) => [s.optionBtn, pressed && s.pressed]} onPress={onDismiss}
        accessibilityRole="button" accessibilityLabel="Ignora la decision">
        <Ionicons name="close-circle-outline" size={16} color={tokens.color.error} />
        <Text style={[s.optionText, { color: tokens.color.error }]}>Ignora</Text>
        <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurfaceMuted} />
      </Pressable>
    </Sheet>
  );
}

// ========== History Sheet ==========
export function HistorySheet({ open, onClose, items }: {
  open: boolean; onClose: () => void; items: DecisionActionHistoryItem[] | null;
}) {
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title="Cronologia" testID="sheet-history">
      {items === null ? (
        <View style={{ padding: 24 }}>
          <ActivityIndicator color={tokens.color.onSurfaceMuted} />
        </View>
      ) : items.length === 0 ? (
        <Text style={s.muted}>Nessun evento registrato.</Text>
      ) : (
        items.map((h) => (
          <View key={h.id} style={s.timelineRow}>
            <View style={s.timelineDot} />
            <View style={{ flex: 1 }}>
              <Text style={s.timelineTitle}>{USER_ACTION_LABELS[h.user_action] || h.user_action}</Text>
              <Text style={s.timelineMeta}>{formatDateTime(h.timestamp)}</Text>
              {h.reason && <Text style={s.timelineNote}>Motivo: {h.reason}</Text>}
              {h.note && <Text style={s.timelineNote}>Nota: {h.note}</Text>}
              {h.completion_percentage != null && <Text style={s.timelineNote}>Progresso: {h.completion_percentage}%</Text>}
            </View>
          </View>
        ))
      )}
    </Sheet>
  );
}

const s = StyleSheet.create({
  whyTitle: { fontSize: 16, color: tokens.color.onSurface, lineHeight: 22 },
  ruleRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start', paddingVertical: 6 },
  ruleDot: { width: 8, height: 8, borderRadius: 4, marginTop: 6 },
  ruleLabel: { fontSize: 14, color: tokens.color.onSurface, fontWeight: '600' },
  ruleEvidence: { fontSize: 12, color: tokens.color.onSurfaceMuted, marginTop: 2, lineHeight: 17 },
  step: { fontSize: 13, color: tokens.color.onSurface, lineHeight: 20 },
  muted: { fontSize: 13, color: tokens.color.onSurfaceMuted },
  statRow: { flexDirection: 'row', gap: 8, marginTop: 6 },
  statBox: { flex: 1, backgroundColor: tokens.color.surfaceTertiary, padding: 12, borderRadius: tokens.radius.md },
  statLabel: { fontSize: 11, color: tokens.color.onSurfaceMuted },
  statValue: { fontSize: 16, color: tokens.color.onSurface, fontWeight: '700', marginTop: 2 },
  sourceRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start', paddingVertical: 6 },
  sourceName: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '600' },
  sourceNotes: { fontSize: 12, color: tokens.color.onSurface, marginTop: 2 },
  sourceMeta: { fontSize: 11, color: tokens.color.onSurfaceMuted, marginTop: 2 },
  actions: { flexDirection: 'row', gap: 8, marginTop: 16 },
  pctBtn: {
    flex: 1, paddingVertical: 12, borderRadius: tokens.radius.md,
    borderWidth: 1, borderColor: tokens.color.border,
    alignItems: 'center', minHeight: tokens.touch.min,
    backgroundColor: tokens.color.surfaceTertiary,
  },
  pctBtnActive: { backgroundColor: tokens.color.brand, borderColor: tokens.color.brand },
  pctBtnText: { color: tokens.color.onSurface, fontWeight: '600' },
  pctBtnTextActive: { color: tokens.color.onBrand },
  input: {
    marginTop: 12, backgroundColor: tokens.color.surfaceTertiary,
    borderRadius: tokens.radius.md, padding: 12,
    color: tokens.color.onSurface, minHeight: tokens.touch.min,
    borderWidth: 1, borderColor: tokens.color.border, fontSize: 14,
  },
  optionBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: tokens.color.border,
    minHeight: tokens.touch.min,
  },
  optionText: { fontSize: 15, color: tokens.color.onSurface, fontWeight: '500', flex: 1 },
  optionMeta: { fontSize: 11, color: tokens.color.onSurfaceMuted },
  timelineRow: { flexDirection: 'row', gap: 12, paddingVertical: 8 },
  timelineDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: tokens.color.brand, marginTop: 4 },
  timelineTitle: { fontSize: 14, color: tokens.color.onSurface, fontWeight: '600' },
  timelineMeta: { fontSize: 11, color: tokens.color.onSurfaceMuted, marginTop: 2 },
  timelineNote: { fontSize: 12, color: tokens.color.onSurfaceMuted, marginTop: 2 },
  pressed: { opacity: 0.7 },
});
