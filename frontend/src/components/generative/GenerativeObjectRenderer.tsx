/**
 * Generic GenerativeObject renderer — UI primitives only.
 * No study/travel/dog domain branches.
 * Colors MUST come from useTheme() — never static dark tokens.color.
 */
import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View, type TextStyle } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import {
  EMPTY_REVEAL_FALLBACK,
  normalizeRevealCardItem,
  normalizeRevealCardItems,
} from './revealCard';

const spacing = tokens.spacing;
const typography = tokens.typography;
const layout = StyleSheet.create({
  root: { gap: spacing.md },
  block: { gap: spacing.xs, marginBottom: spacing.sm },
  section: { gap: spacing.sm, marginBottom: spacing.md },
  deck: { gap: spacing.sm, marginBottom: spacing.md },
  row: { flexDirection: 'row', justifyContent: 'space-between' },
  timelineRow: { marginBottom: spacing.sm, gap: 2 },
  taskRow: { paddingVertical: 4 },
});

type Block = Record<string, any>;

type Props = {
  content?: { blocks?: Block[] } | null;
  objectId?: string;
  onInteract?: (eventType: string, payload: Record<string, unknown>) => void;
};

export function GenerativeObjectRenderer({ content, objectId, onInteract }: Props) {
  const { colors } = useTheme();
  const blocks = content?.blocks || [];
  if (!blocks.length) {
    return (
      <Text style={[typography.caption, { color: colors.textSecondary }]}>
        Nessun contenuto strutturato.
      </Text>
    );
  }
  return (
    <View style={layout.root}>
      {blocks.map((b, i) => (
        <BlockView
          key={b.id || `${b.type}-${i}`}
          block={b}
          objectId={objectId}
          onInteract={onInteract}
        />
      ))}
    </View>
  );
}

function BlockView({
  block,
  objectId,
  onInteract,
}: {
  block: Block;
  objectId?: string;
  onInteract?: Props['onInteract'];
}) {
  const { colors } = useTheme();
  const t = String(block.type || '');
  const body: TextStyle[] = [typography.body, { color: colors.textPrimary }];
  const bodyStrong: TextStyle[] = [
    typography.body,
    { color: colors.textPrimary, fontWeight: '600' },
  ];
  const muted: TextStyle[] = [typography.caption, { color: colors.textSecondary }];

  if (t === 'heading') {
    return (
      <Text
        style={[
          typography.headline,
          { color: colors.textPrimary, marginBottom: spacing.sm },
        ]}
      >
        {block.text || block.heading || ''}
      </Text>
    );
  }
  if (t === 'text' || t === 'callout') {
    return (
      <View
        style={
          t === 'callout'
            ? {
                padding: spacing.md,
                borderLeftWidth: 2,
                borderLeftColor: colors.border,
                backgroundColor: colors.surfaceElevated || colors.surface,
              }
            : undefined
        }
      >
        <Text style={body}>{block.text || block.body || ''}</Text>
      </View>
    );
  }
  if (t === 'section') {
    return (
      <View style={layout.section}>
        {block.title || block.heading ? (
          <Text style={[typography.label, { color: colors.textPrimary }]}>
            {block.title || block.heading}
          </Text>
        ) : null}
        {(block.children || []).map((c: Block, i: number) => (
          <BlockView key={c.id || i} block={c} objectId={objectId} onInteract={onInteract} />
        ))}
      </View>
    );
  }
  if (t === 'list' || t === 'ordered_list') {
    const items = block.items || [];
    return (
      <View style={layout.block}>
        {items.map((it: any, i: number) => (
          <Text key={i} style={body}>
            {t === 'ordered_list' ? `${i + 1}. ` : '· '}
            {typeof it === 'string' ? it : it?.label || it?.text || ''}
          </Text>
        ))}
      </View>
    );
  }
  if (t === 'card_deck') {
    return <CardDeck items={block.items || []} onInteract={onInteract} />;
  }
  if (t === 'card') {
    return <CardDeck items={[block]} onInteract={onInteract} />;
  }
  if (t === 'timeline') {
    return (
      <View style={layout.block}>
        {(block.items || []).map((it: any, i: number) => (
          <View key={i} style={layout.timelineRow}>
            <Text style={muted}>{it.when || ''}</Text>
            <Text style={bodyStrong}>{it.label || ''}</Text>
            {it.detail ? <Text style={body}>{it.detail}</Text> : null}
          </View>
        ))}
      </View>
    );
  }
  if (t === 'task_group' || t === 'task') {
    const items =
      t === 'task'
        ? [{ label: block.label || block.text, done: block.done }]
        : block.items || [];
    return (
      <View style={layout.block}>
        {items.map((it: any, i: number) => (
          <Pressable
            key={i}
            onPress={() =>
              onInteract?.('check', {
                index: i,
                label: it.label || it.text,
                done: !it.done,
              })
            }
            style={layout.taskRow}
          >
            <Text style={body}>
              {it.done ? '☑' : '☐'} {it.label || it.text || ''}
            </Text>
          </Pressable>
        ))}
      </View>
    );
  }
  if (t === 'relation_graph') {
    return (
      <View style={layout.block}>
        <Text style={bodyStrong}>Relazioni</Text>
        {(block.nodes || []).map((n: any) => (
          <Text key={n.id} style={body}>
            • {n.label}
            {n.description ? ` — ${n.description}` : ''}
          </Text>
        ))}
        {(block.edges || []).map((e: any, i: number) => (
          <Text key={i} style={muted}>
            {e.source} → {e.target}
            {e.relation ? ` (${e.relation})` : ''}
          </Text>
        ))}
      </View>
    );
  }
  if (t === 'question' || t === 'answer_reveal') {
    return <RevealQA block={block} onInteract={onInteract} />;
  }
  if (t === 'choice') {
    return (
      <View style={layout.block}>
        <Text style={bodyStrong}>{block.prompt || ''}</Text>
        {(block.options || []).map((o: string, i: number) => (
          <Pressable
            key={i}
            onPress={() => onInteract?.('select', { index: i, option: o })}
            style={{
              paddingVertical: spacing.sm,
              borderBottomWidth: StyleSheet.hairlineWidth,
              borderBottomColor: colors.border,
            }}
          >
            <Text style={body}>{o}</Text>
          </Pressable>
        ))}
      </View>
    );
  }
  if (t === 'key_value') {
    return (
      <View style={layout.block}>
        {(block.pairs || []).map((p: any, i: number) => (
          <Text key={i} style={body}>
            <Text style={bodyStrong}>{p.key}: </Text>
            {p.value}
          </Text>
        ))}
      </View>
    );
  }
  if (t === 'table') {
    return (
      <View style={layout.block}>
        <Text style={muted}>{(block.headers || []).join(' · ')}</Text>
        {(block.rows || []).map((row: any[], i: number) => (
          <Text key={i} style={body}>
            {(row || []).join(' · ')}
          </Text>
        ))}
      </View>
    );
  }
  if (t === 'formula' || t === 'code') {
    return (
      <Text
        style={[
          typography.caption,
          {
            color: colors.textPrimary,
            fontFamily: 'monospace',
            marginBottom: spacing.sm,
          },
        ]}
      >
        {block.formula || block.text || block.code || ''}
      </Text>
    );
  }
  if (t === 'source') {
    return (
      <Text style={muted}>
        Fonte: {block.label || ''} {block.url ? `— ${block.url}` : ''}
      </Text>
    );
  }
  if (t === 'progress') {
    return (
      <Text style={body}>
        {block.label || 'Progresso'}: {Math.round(Number(block.value || 0) * 100)}%
      </Text>
    );
  }
  if (t === 'divider') {
    return (
      <View
        style={{
          height: StyleSheet.hairlineWidth,
          backgroundColor: colors.border,
          marginVertical: spacing.md,
        }}
      />
    );
  }
  return <Text style={muted}>Blocco non supportato: {t || 'unknown'}</Text>;
}

function CardDeck({
  items,
  onInteract,
}: {
  items: any[];
  onInteract?: Props['onInteract'];
}) {
  const { colors } = useTheme();
  const cards = useMemo(() => normalizeRevealCardItems(items), [items]);
  const [idx, setIdx] = useState(0);
  const [revealed, setRevealed] = useState(false);
  if (!cards.length) return null;
  const safeIdx = Math.min(Math.max(0, idx), cards.length - 1);
  const card = cards[safeIdx] || normalizeRevealCardItem(null);
  const showReveal = card.revealable;
  const backText = card.back || EMPTY_REVEAL_FALLBACK;
  const body: TextStyle[] = [typography.body, { color: colors.textPrimary }];
  const bodyStrong: TextStyle[] = [
    typography.body,
    { color: colors.textPrimary, fontWeight: '600' },
  ];
  const muted: TextStyle[] = [typography.caption, { color: colors.textSecondary }];
  const link: TextStyle[] = [
    typography.body,
    { color: colors.textPrimary, textDecorationLine: 'underline' },
  ];

  return (
    <View style={layout.deck}>
      <Text style={muted}>
        {safeIdx + 1}/{cards.length}
      </Text>
      {card.label ? <Text style={muted}>{card.label}</Text> : null}
      <Pressable
        disabled={!showReveal}
        onPress={() => {
          if (!showReveal) return;
          const next = !revealed;
          setRevealed(next);
          onInteract?.('reveal', { index: safeIdx, revealed: next });
        }}
        style={{
          padding: spacing.lg,
          borderWidth: StyleSheet.hairlineWidth,
          borderColor: colors.border,
          borderRadius: 12,
          minHeight: 120,
          justifyContent: 'center',
          gap: spacing.sm,
          backgroundColor: colors.surface || colors.backgroundSecondary,
        }}
      >
        <Text style={bodyStrong}>{card.front}</Text>
        {showReveal ? (
          revealed ? (
            <Text style={body}>{backText}</Text>
          ) : (
            <Text style={muted}>Tocca per rivelare</Text>
          )
        ) : null}
      </Pressable>
      {cards.length > 1 ? (
        <View style={layout.row}>
          <Pressable
            onPress={() => {
              setIdx((i) => Math.max(0, i - 1));
              setRevealed(false);
              onInteract?.('next_previous', { index: Math.max(0, safeIdx - 1) });
            }}
          >
            <Text style={link}>Precedente</Text>
          </Pressable>
          <Pressable
            onPress={() => {
              setIdx((i) => Math.min(cards.length - 1, i + 1));
              setRevealed(false);
              onInteract?.('next_previous', {
                index: Math.min(cards.length - 1, safeIdx + 1),
              });
            }}
          >
            <Text style={link}>Successiva</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

function RevealQA({
  block,
  onInteract,
}: {
  block: Block;
  onInteract?: Props['onInteract'];
}) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const body: TextStyle[] = [typography.body, { color: colors.textPrimary }];
  const bodyStrong: TextStyle[] = [
    typography.body,
    { color: colors.textPrimary, fontWeight: '600' },
  ];
  const link: TextStyle[] = [
    typography.body,
    { color: colors.textPrimary, textDecorationLine: 'underline' },
  ];
  return (
    <View style={layout.block}>
      <Text style={bodyStrong}>{block.prompt || block.text || ''}</Text>
      <Pressable
        onPress={() => {
          setOpen((v) => !v);
          onInteract?.('reveal', { open: !open });
        }}
      >
        <Text style={link}>{open ? 'Nascondi' : 'Mostra risposta'}</Text>
      </Pressable>
      {open ? <Text style={body}>{block.answer || ''}</Text> : null}
    </View>
  );
}
