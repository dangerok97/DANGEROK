import React from 'react';
import { Text, View } from 'react-native';

type Props = { onCapture: (dataUri: string) => void; onError: (message: string) => void };

/** The web camera is not silently represented as native AR.
 * Use the photo picker on native until camera permissions and native builds exist.
 */
export default function CameraPreview(_props: Props) {
  return (
    <View style={{ padding: 16, borderRadius: 12, backgroundColor: '#121926' }}>
      <Text style={{ color: '#FFFFFF', lineHeight: 22 }}>
        Fotocamera dal vivo disponibile su ORA Web. Qui puoi usare «Scegli foto» per analizzare un’immagine.
      </Text>
    </View>
  );
}
