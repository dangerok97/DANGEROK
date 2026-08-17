export type GoogleAuthAvailabilityStatus =
  | 'ready'
  | 'missing_frontend_config'
  | 'unsupported'
  | 'loading'
  | 'error';

export type GoogleAuthAvailability = {
  status: GoogleAuthAvailabilityStatus;
  safeMessage?: string;
};

export type GoogleAuthSuccess = {
  ok: true;
  idToken: string;
  nonce?: string;
};

export type GoogleAuthFailure = {
  ok: false;
  code: string;
  safeMessage: string;
  cancelled: boolean;
};

export type GoogleAuthResult = GoogleAuthSuccess | GoogleAuthFailure;

export type GoogleAuthAdapter = {
  availability: GoogleAuthAvailability;
  signIn: () => Promise<GoogleAuthResult>;
  renderButton?: (
    container: HTMLElement,
    onResult: (result: GoogleAuthResult) => void,
    options?: { width?: number },
  ) => Promise<void>;
};
