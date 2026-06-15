import { memo } from "react";

export const MeshGradientBackground = memo(function MeshGradientBackground() {
  return (
    <>
      <style>{`
        .mesh-bg {
          position: fixed;
          inset: 0;
          z-index: -1;
          overflow: hidden;
          background: var(--mesh-base);
          transition: background 0.8s ease;
        }

        .mesh-blob {
          position: absolute;
          border-radius: 50%;
          filter: blur(120px);
          opacity: var(--mesh-opacity, 0.55);
          will-change: transform;
          transition: background 0.8s ease, opacity 0.8s ease;
        }

        .mesh-blob-1 {
          width: 55vmax;
          height: 55vmax;
          top: -18%;
          left: -12%;
          background: var(--blob-1);
          animation: meshFloat1 18s ease-in-out infinite;
        }

        .mesh-blob-2 {
          width: 48vmax;
          height: 48vmax;
          bottom: -15%;
          right: -10%;
          background: var(--blob-2);
          animation: meshFloat2 22s ease-in-out infinite;
        }

        .mesh-blob-3 {
          width: 42vmax;
          height: 42vmax;
          top: 40%;
          left: 35%;
          background: var(--blob-3);
          animation: meshFloat3 20s ease-in-out infinite;
        }

        @keyframes meshFloat1 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33%      { transform: translate(8vw, 6vh) scale(1.08); }
          66%      { transform: translate(-4vw, 10vh) scale(0.95); }
        }

        @keyframes meshFloat2 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33%      { transform: translate(-10vw, -5vh) scale(1.06); }
          66%      { transform: translate(5vw, -8vh) scale(0.94); }
        }

        @keyframes meshFloat3 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33%      { transform: translate(6vw, -7vh) scale(1.1); }
          66%      { transform: translate(-8vw, 5vh) scale(0.92); }
        }

        @media (prefers-reduced-motion: reduce) {
          .mesh-blob { animation: none !important; }
        }
      `}</style>
      <div className="mesh-bg" aria-hidden="true">
        <div className="mesh-blob mesh-blob-1" />
        <div className="mesh-blob mesh-blob-2" />
        <div className="mesh-blob mesh-blob-3" />
      </div>
    </>
  );
});
