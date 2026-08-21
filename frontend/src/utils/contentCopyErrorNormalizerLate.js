import axios from 'axios';
import { normalizeContentCopyError } from '@/utils/contentCopyErrorNormalizer';

// P0 21/08/2026 — esta barreira precisa ser registrada DEPOIS do
// contentDvdBridge. Assim ela também recebe rejeições geradas dentro dos
// interceptors de resposta do bridge (por exemplo, publicação automática
// subsequente a uma cópia) antes que um objeto `detail` chegue ao React.
axios.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(normalizeContentCopyError(error)),
);
