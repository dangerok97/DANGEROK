import React from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { tokens } from '@/src/theme/tokens';

/** Native capture is not silently substituted with a static photograph. */
export default function LiveExplorer() {
  const router = useRouter();
  const [error, setError] = React.useState('');
  return <View style={styles.root}>
    <Text style={styles.title}>ORA Vision</Text>
    <Text style={styles.text}>Questa prima versione della fotocamera live è disponibile su ORA Web. Il catalogo è condiviso, ma la fotocamera nativa non è ancora collegata.</Text>
    <Pressable style={styles.button} onPress={() => { void Linking.openURL('https://ora-web-production-fb67.up.railway.app/vision-xray').catch(() => setError('Impossibile aprire il browser.')); }}><Text style={styles.buttonText}>Apri ORA Web</Text></Pressable>
    {!!error && <Text style={styles.text}>{error}</Text>}
    <Pressable style={styles.button} onPress={() => router.back()}><Text style={styles.buttonText}>Torna indietro</Text></Pressable>
  </View>;
}
const styles = StyleSheet.create({
  root: {flex:1,justifyContent:'center',padding:26,gap:18,backgroundColor:tokens.color.backgroundPrimary},
  title:{fontSize:30,fontWeight:'700',color:tokens.color.textPrimary},
  text:{fontSize:16,lineHeight:24,color:tokens.color.textSecondary},
  button:{minHeight:48,padding:14,borderRadius:12,backgroundColor:tokens.color.accent,alignItems:'center'},
  buttonText:{fontSize:15,fontWeight:'600',color:tokens.color.onAccent},
});
