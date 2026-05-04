/**
 * useTenantBranding — wrapper retrocompatível.
 *
 * Sprint G4 (Mai/2026): a lógica real foi movida para `BrandingContext`,
 * que carrega 1× no app-level e fornece via `useBranding()`. Este hook
 * permanece como façade para não quebrar callers existentes.
 */
import { useBranding } from '@/contexts/BrandingContext';

export default function useTenantBranding() {
  return useBranding();
}
