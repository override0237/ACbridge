import { ArrowRight } from 'lucide-react-native';
import { StatusBar } from 'expo-status-bar';
import { ScrollView, View } from 'react-native';
import { Logo } from '../components/Logo';
import { Badge, Body, Button, Card } from '../components/primitives';
import { useTheme } from '../theme/useTheme';

/** Phase 1 shell: shows the primitives in the current system mode. Navigation, auth and screens arrive in later phases. */
export default function App() {
  const t = useTheme();
  return (
    <View style={{ flex: 1, backgroundColor: t.colors.surface }}>
      <StatusBar style="light" />
      <View style={{ backgroundColor: t.colors.ink, paddingHorizontal: t.space[4], paddingVertical: t.space[3], borderBottomWidth: 3, borderBottomColor: t.colors.goldDeep }}><Logo tone="on-ink" height={32} /></View>
      <ScrollView contentContainerStyle={{ padding: t.space[4], gap: t.space[4] }}>
        <Card title="ACbridge">
          <Body>Trusted artisans near you.</Body>
          <Badge tone="success">Verified</Badge>
          <Button icon={ArrowRight} label="Continue" onPress={() => undefined} />
        </Card>
      </ScrollView>
    </View>
  );
}
