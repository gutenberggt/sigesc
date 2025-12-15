import { AlertTriangle } from 'lucide-react';
import { Modal } from '@/components/Modal';
import { Button } from '@/components/ui/button';

export const DeleteConfirmModal = ({
  isOpen,
  onClose,
  onConfirm,
  deleting
}) => {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Confirmar Exclusão"
    >
      <div className="space-y-4">
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-start gap-3">
            <AlertTriangle className="text-red-500 mt-0.5" size={20} />
            <div>
              <div className="font-medium text-red-800">Tem certeza que deseja excluir?</div>
              <div className="text-sm text-red-600 mt-1">Esta ação não pode ser desfeita.</div>
            </div>
          </div>
        </div>
        
        <div className="flex gap-2">
          <Button 
            onClick={onConfirm} 
            disabled={deleting}
            className="flex-1 bg-red-600 hover:bg-red-700"
          >
            {deleting ? 'Excluindo...' : 'Sim, Excluir'}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
        </div>
      </div>
    </Modal>
  );
};

export default DeleteConfirmModal;
