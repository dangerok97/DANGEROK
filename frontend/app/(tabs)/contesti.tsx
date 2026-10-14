/** Backward compatible address for the single VITA experience.
 * VITA's canonical route is /vita; never fork this into a second screen.
 * Old bookmarks and deep links now converge without duplicating user data.
 */
import { Redirect } from 'expo-router';

export default function LegacyContestiRedirect() {
  return <Redirect href="/vita" />;
}
