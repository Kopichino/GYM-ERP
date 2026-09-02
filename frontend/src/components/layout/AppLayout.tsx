import { AnimatePresence, motion } from "framer-motion";
import { Outlet, useLocation } from "react-router-dom";
import { pageTransition } from "../../lib/motion";
import Navbar from "./Navbar";

export default function AppLayout() {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <Navbar />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial="initial"
            animate="animate"
            exit="exit"
            variants={pageTransition}
            transition={{ duration: 0.25, ease: "easeInOut" }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
