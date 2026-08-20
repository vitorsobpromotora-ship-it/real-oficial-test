// Miniatura real do corte (frame do meio, servida pelo motor com cache).
import { useEffect, useState } from "react";
import { mediaUrl } from "../api/client";

export default function Thumb({ cutId, className }: { cutId: string; className?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [erro, setErro] = useState(false);
  useEffect(() => {
    let vivo = true;
    mediaUrl(`/api/v1/media/cuts/${cutId}/thumb`).then((u) => vivo && setUrl(u));
    return () => {
      vivo = false;
    };
  }, [cutId]);
  if (erro || !url) return <div className={`thumb-ph ${className ?? ""}`}>🎬</div>;
  return (
    <img className={`thumb ${className ?? ""}`} src={url} alt="" loading="lazy"
         draggable={false} onError={() => setErro(true)} />
  );
}
