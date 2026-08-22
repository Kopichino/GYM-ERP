import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import Hero3D from "../components/three/Hero3D";

const features = [
  { title: "Self-service check-in", copy: "Tap in, tap out. Your visit is logged automatically -- no more sign-in sheets." },
  { title: "Workout logging", copy: "Track every set, rep, and weight, exercise by exercise." },
  { title: "Progress tracker", copy: "Watch your lifts trend upward with visual charts over time." },
  { title: "Community gallery", copy: "Share your gym moments with photos and videos." },
  { title: "Live announcements", copy: "Never miss a gym update or class change again." },
  { title: "Class schedule", copy: "See upcoming sessions and the instructors running them." },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen overflow-x-hidden bg-[var(--color-bg)]">
      <section className="relative flex min-h-screen flex-col items-center justify-center px-4 text-center">
        <Hero3D />
        <div className="relative z-10">
          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="mb-3 text-sm font-semibold uppercase tracking-[0.3em] text-[var(--color-accent-2)]"
          >
            Your gym, digitized
          </motion.p>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="text-5xl font-black tracking-tight text-[var(--color-text)] sm:text-7xl"
          >
            IRON<span className="text-[var(--color-accent)]">CORE</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="mx-auto mt-4 max-w-xl text-lg text-[var(--color-text-muted)]"
          >
            Check in, log your lifts, track your progress, and stay connected with your gym
            community -- all in one place.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.3 }}
            className="mt-8 flex justify-center gap-4"
          >
            <Link
              to="/signup"
              className="rounded-md bg-[var(--color-accent)] px-6 py-3 text-sm font-semibold text-white hover:opacity-90"
            >
              Get Started
            </Link>
            <Link
              to="/login"
              className="rounded-md border border-[var(--color-border)] px-6 py-3 text-sm font-semibold text-[var(--color-text)] hover:border-[var(--color-accent)]"
            >
              Log In
            </Link>
          </motion.div>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 pb-24">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.5, delay: i * 0.05 }}
              className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
            >
              <h3 className="mb-2 font-semibold text-[var(--color-text)]">{f.title}</h3>
              <p className="text-sm text-[var(--color-text-muted)]">{f.copy}</p>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  );
}
