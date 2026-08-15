import TutorialSecretario from './TutorialSecretario';

// Compatibilidade: preserva a URL pública antiga
// /tutoriais/secretarios/acesso, agora usando a trilha atualizada.
export default function TutorialAcesso() {
  return <TutorialSecretario slug="primeiros-passos" />;
}
