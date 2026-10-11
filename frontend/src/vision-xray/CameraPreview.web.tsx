import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

type Props = { onCapture: (dataUri: string) => void; onError: (message: string) => void };

/** Browser camera: user opts in, one still is analysed, stream is then stopped. */
export default function CameraPreview({ onCapture, onError }: Props) {
  const video = useRef<HTMLVideoElement | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const attempted = useRef(false);
  const onCaptureRef = useRef(onCapture);
  const onErrorRef = useRef(onError);
  const [ready, setReady] = useState(false);
  onCaptureRef.current = onCapture;
  onErrorRef.current = onError;

  const snapshot = useCallback(() => {
    if (attempted.current) return;
    const current = video.current;
    if (!current || !current.videoWidth || !current.videoHeight) {
      onErrorRef.current('Inquadra un oggetto e riprova.');
      return;
    }
    attempted.current = true;
    const canvas = document.createElement('canvas');
    const ratio = Math.min(1, 1280 / Math.max(current.videoWidth, current.videoHeight));
    canvas.width = Math.round(current.videoWidth * ratio);
    canvas.height = Math.round(current.videoHeight * ratio);
    const context = canvas.getContext('2d');
    if (!context) {
      attempted.current = false;
      onErrorRef.current('Impossibile catturare l’immagine.');
      return;
    }
    context.drawImage(current, 0, 0, canvas.width, canvas.height);
    const image = canvas.toDataURL('image/jpeg', 0.82);
    // Camera stops as soon as the parent freezes this frame.
    onCaptureRef.current(image);
  }, []);

  useEffect(() => {
    let active = true;
    let autoTimer: ReturnType<typeof setTimeout> | null = null;
    const start = async () => {
      if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) {
        onErrorRef.current('La fotocamera richiede HTTPS e un browser compatibile.');
        return;
      }
      try {
        const media = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } },
        });
        if (!active) {
          media.getTracks().forEach((track) => track.stop());
          return;
        }
        stream.current = media;
        if (video.current) {
          video.current.srcObject = media;
          await video.current.play();
        }
        if (!active) return;
        setReady(true);
        // Once the user explicitly opened camera, recognise after a short aiming window.
        autoTimer = setTimeout(snapshot, 3800);
      } catch {
        if (active) onErrorRef.current('Accesso alla fotocamera negato o non disponibile.');
      }
    };
    void start();
    return () => {
      active = false;
      if (autoTimer) clearTimeout(autoTimer);
      stream.current?.getTracks().forEach((track) => track.stop());
      stream.current = null;
    };
  }, [snapshot]);

  return (
    <View style={styles.root} testID="vision-live-camera">
      {React.createElement('video', {
        ref: video,
        autoPlay: true,
        muted: true,
        playsInline: true,
        'aria-label': 'Fotocamera di ORA',
        style: { width: '100%', height: 300, objectFit: 'cover', borderRadius: 16, background: '#090e1a' },
      })}
      <View style={styles.bottom}>
        <Text style={styles.hint}>{ready ? 'Inquadra l’oggetto · riconoscimento automatico' : 'Attivo la fotocamera…'}</Text>
        <Pressable disabled={!ready} onPress={snapshot} style={[styles.trigger, !ready && { opacity: 0.6 }]}>
          {ready ? <Text style={styles.triggerText}>Analizza ora</Text> : <ActivityIndicator color="#ffffff" />}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { width: '100%', overflow: 'hidden', borderRadius: 16, backgroundColor: '#101725' },
  bottom: { padding: 14, gap: 10 },
  hint: { color: '#D4DFEC', fontSize: 13, textAlign: 'center' },
  trigger: { alignItems: 'center', justifyContent: 'center', minHeight: 48, borderRadius: 12, backgroundColor: '#416CEF' },
  triggerText: { color: '#FFFFFF', fontWeight: '700', fontSize: 14 },
});
