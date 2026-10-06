import { useEffect, useLayoutEffect, useState, type RefObject } from 'react';
import { Keyboard, Platform, type View } from 'react-native';
import { remainingVisualHeight } from './mobileConversationLayout';

/** The mobile browser keyboard changes visualViewport, not necessarily innerHeight.
 * Scope this measurement to the conversation root; never change global body styles.
 * Pinch zoom remains accessible and must not be mistaken for opening the keyboard.
 */
export function useConversationViewport(root: RefObject<View | null>, bottomInset = 0) {
  const [editing, setEditing] = useState(false);
  const [maxHeight, setMaxHeight] = useState<number | null>(null);

  useEffect(() => {
    if (Platform.OS === 'web') return;
    const show = Keyboard.addListener('keyboardDidShow', () => setEditing(true));
    const hide = Keyboard.addListener('keyboardDidHide', () => setEditing(false));
    return () => { show.remove(); hide.remove(); };
  }, []);

  useLayoutEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined' || typeof document === 'undefined') return;
    let frame = 0;
    let alive = true;
    const viewport = window.visualViewport;
    const read = () => {
      frame = 0;
      if (!alive) return;
      const element = root.current as unknown as HTMLElement | null;
      if (!element?.getBoundingClientRect) return;
      const focused = document.activeElement as HTMLElement | null;
      const isTextEntry = !!focused && element.contains(focused) && (
        focused.tagName === 'TEXTAREA' || focused.tagName === 'INPUT' || focused.isContentEditable
      );
      setEditing(isTextEntry);
      // Let the browser handle magnification normally.
      if (viewport && Math.abs(viewport.scale - 1) > 0.05) {
        setMaxHeight(null);
        return;
      }
      const next = remainingVisualHeight(
        viewport?.height ?? window.innerHeight,
        viewport?.offsetTop ?? 0,
        element.getBoundingClientRect().top,
        bottomInset,
      );
      setMaxHeight(previous => previous === next ? previous : next);
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(read);
    };
    schedule();
    viewport?.addEventListener('resize', schedule);
    viewport?.addEventListener('scroll', schedule);
    window.addEventListener('resize', schedule);
    document.addEventListener('focusin', schedule);
    document.addEventListener('focusout', schedule);
    return () => {
      alive = false;
      if (frame) window.cancelAnimationFrame(frame);
      viewport?.removeEventListener('resize', schedule);
      viewport?.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      document.removeEventListener('focusin', schedule);
      document.removeEventListener('focusout', schedule);
    };
  }, [root, bottomInset]);
  return { editing, maxHeight };
}
