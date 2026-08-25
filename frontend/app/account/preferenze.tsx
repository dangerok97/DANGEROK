/**
 * Preferenze ORA — how ORA works with your things.
 *
 * The reference composition for this page has a response style, a tone of
 * voice and a proactive-suggestions switch. None of the three is stored
 * anywhere in ORA: there is no persisted style, no persisted tone, and
 * proactivity is decided by the engines from context rather than from a
 * setting. Inventing them would give someone a dial that turns and changes
 * nothing, which is worse than a short page.
 *
 * What is real is `document_ai_analysis`: the analyzer reads it before every
 * document and does nothing when it is off. So this page has one preference,
 * and it is a true one.
 */
import { useCallback, useEffect, useState } from 'react';

import { api } from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';
import { haptic } from '@/src/utils/haptic';
import {
  BoundaryNote,
  Footnote,
  DOCUMENT_SCOPE_BOUNDARY,
  InlineError,
  SettingCard,
  SubpageShell,
  ToggleRow,
} from '@/src/components/account';

export default function PreferenzeScreen() {
  const [analysis, setAnalysis] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .documentPreferences()
      .then((p) => {
        if (alive) setAnalysis(p.document_ai_analysis !== false);
      })
      .catch((e: any) => {
        if (alive) setError(humanizeError(e, 'default'));
      });
    return () => {
      alive = false;
    };
  }, []);

  const toggle = useCallback(async (next: boolean) => {
    haptic('tap');
    setBusy(true);
    setError(null);
    // Optimistic: the switch answers immediately and corrects itself if the
    // write is refused, rather than sitting inert while a request travels.
    setAnalysis(next);
    try {
      const res = await api.setDocumentPreferences({ document_ai_analysis: next });
      setAnalysis(res.document_ai_analysis !== false);
      haptic('success');
    } catch (e: any) {
      setAnalysis(!next);
      haptic('error');
      setError(humanizeError(e, 'default'));
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <SubpageShell
      title="Preferenze ORA"
      subtitle="Scegli come ORA lavora con le tue cose."
      testID="account-preferences"
    >
      {analysis === null ? (
        <SettingCard
          title="Documenti"
          detail={error ? 'Non riesco a leggere questa preferenza in questo momento.' : 'Carico…'}
        />
      ) : (
        <SettingCard title="Documenti" testID="pref-documents">
          <ToggleRow
            label="Lascia che ORA legga i tuoi documenti"
            detail={
              analysis
                ? 'ORA riassume ciò che contengono, riconosce le scadenze e li collega alla parte di vita a cui appartengono.'
                : 'I documenti restano salvati, ma ORA non li apre né li usa per capire il tuo contesto.'
            }
            value={analysis}
            onChange={(v) => void toggle(v)}
            busy={busy}
            testID="pref-document-analysis"
          />
          <BoundaryNote icon="lock-closed-outline">{DOCUMENT_SCOPE_BOUNDARY}</BoundaryNote>
        </SettingCard>
      )}

      {error ? <InlineError>{error}</InlineError> : null}

      {/*
        Why the page is short. A statement about how ORA works, not a promise
        about what will be added to it.
      */}
      <Footnote>
        ORA sceglie il tono e il momento in cui parlarti leggendo il contesto, non
        un’impostazione.
      </Footnote>
    </SubpageShell>
  );
}
