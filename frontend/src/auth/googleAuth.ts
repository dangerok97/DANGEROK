// TypeScript/Web-safe fallback. Metro resolves googleAuth.web.ts on Web and
// googleAuth.native.ts on iOS/Android; if a resolver selects this generic file,
// it must never pull the native Google Sign-In package into a Web bundle.
export { useGoogleAuth } from './googleAuth.web';
