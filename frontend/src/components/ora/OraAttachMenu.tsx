/** The attachment channels stay intact; Vision opens ORA's continuous camera. */
import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

export type AttachKind = 'any' | 'photo' | 'camera' | 'document';
type Entry = {
  kind: AttachKind;
  icon: React.ComponentProps<typeof Ionicons>['name'];
  title: string;
  hint: string;
};
export function cameraOpens(): boolean {
  if (Platform.OS !== 'web') return false;
  if (typeof navigator === 'undefined') return false;
  return /iphone|ipad|ipod|android/i.test(navigator.userAgent || '');
}
export function attachEntries(): Entry[] {
  const all: Entry[] = [
    { kind: 'any', icon: 'albums-outline', title: 'Foto e file', hint: 'Carica dal dispositivo' },
    { kind: 'photo', icon: 'image-outline', title: 'Foto', hint: 'Scegli dalla libreria' },
    { kind: 'camera', icon: 'camera-outline', title: 'Fotocamera', hint: 'Scatta una foto' },
    { kind: 'document', icon: 'document-text-outline', title: 'Documenti', hint: 'Aggiungi un documento' },
  ];
  return all.filter((e) => e.kind !== 'camera' || cameraOpens());
}
type Props = { open: boolean; onClose: () => void; onChoose: (kind: AttachKind) => void; testID: string; lift?: number };

export function OraAttachMenu({ open, onClose, onChoose, testID, lift = 52 }: Props) {
  const { colors } = useTheme();
  const router = useRouter();
  React.useEffect(() => {
    if (!open || Platform.OS !== 'web') return;
    if (typeof document === 'undefined') return;
    const onKey = (e: any) => {
      if (e?.key === 'Escape') { e.preventDefault?.(); onClose(); }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return <>
    <Pressable focusable={false}
      {...(Platform.OS === 'web' ? ({ tabIndex: -1 } as any) : {})}
      accessibilityElementsHidden importantForAccessibility="no-hide-descendants"
      onPress={onClose} style={styles.veil} testID={`${testID}-veil`} />
    <View accessibilityRole="menu" style={[styles.sheet, {bottom: lift, backgroundColor: colors.surfaceElevated || colors.surface, borderColor: colors.border}]} testID={testID}>
      {Platform.OS === 'web' && <Pressable
        accessibilityRole="menuitem" accessibilityLabel="Visione live. Riconosci e scomponi un oggetto nella fotocamera."
        testID={`${testID}-vision`} onPress={() => { onClose(); router.push('/vision-xray'); }}
        style={({pressed,hovered}:any) => [styles.row,(pressed||hovered)&&{backgroundColor:colors.backgroundSecondary}]}>
        <Ionicons name="scan-outline" size={20} color={colors.textSecondary}/>
        <View style={styles.words}><Text style={[styles.title,{color:colors.textPrimary}]}>Visione live</Text><Text style={[styles.hint,{color:colors.textTertiary}]}>Inquadra e scomponi un oggetto</Text></View>
      </Pressable>}
      {attachEntries().map((entry) => (
        <Pressable key={entry.kind} accessibilityRole="menuitem" accessibilityLabel={`${entry.title}. ${entry.hint}`}
          onPress={() => {
            onClose();
            onChoose(entry.kind);
          }}
          style={({pressed,hovered}:any) => [styles.row,(pressed||hovered)&&{backgroundColor:colors.backgroundSecondary}]}
          testID={`${testID}-${entry.kind}`}>
          <Ionicons name={entry.icon} size={20} color={colors.textSecondary}/>
          <View style={styles.words}><Text style={[styles.title,{color:colors.textPrimary}]}>{entry.title}</Text><Text style={[styles.hint,{color:colors.textTertiary}]}>{entry.hint}</Text></View>
        </Pressable>
      ))}
    </View>
  </>;
}
const styles = StyleSheet.create({
  veil: {position:'absolute',top:-4000,left:-4000,right:-4000,bottom:-4000},
  sheet: {
    position:'absolute',left:0,minWidth:244,maxWidth: '92%',borderRadius:tokens.radius.lg,
    borderWidth:StyleSheet.hairlineWidth,paddingVertical:6,overflow:'hidden',
    ...(Platform.OS === 'web' ? {boxShadow:'0 12px 32px rgba(0,0,0,0.10)' as any}
      : {shadowColor:'#000',shadowOpacity:.12,shadowRadius:18,shadowOffset:{width:0,height:8},elevation:8}),
  },
  row:{flexDirection:'row',alignItems:'center',gap:12,minHeight: tokens.touch.min,paddingHorizontal:14,paddingVertical:8},
  words:{flexShrink:1},title:{fontSize:15,lineHeight:20},hint:{fontSize:12,lineHeight:16,marginTop:1},
});
