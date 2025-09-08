import React, { useState } from "react";

function DeployButton() {
  const [status, setStatus] = useState("");

  const handleDeploy = async () => {
    setStatus("Enviando...");
    try {
      const response = await fetch(
        "https://api.vercel.com/v1/integrations/deploy/prj_nwSamZ9QyVv6OsCvsJy6FU9jInKQ/gJEE8NvGDd",
        {
          method: "POST",
        }
      );

      if (response.ok) {
        setStatus("✅ Deploy iniciado com sucesso!");
      } else {
        setStatus("❌ Erro ao iniciar deploy.");
      }
    } catch (error) {
      console.error(error);
      setStatus("❌ Erro ao conectar com o Vercel.");
    }
  };

  return (
    <div className="text-center mt-4">
      <button
        onClick={handleDeploy}
        className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
      >
        Publicar agora
      </button>
      {status && <p className="mt-2 text-sm text-gray-600">{status}</p>}
    </div>
  );
}

export default DeployButton;
