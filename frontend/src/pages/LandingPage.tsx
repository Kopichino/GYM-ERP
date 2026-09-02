import { motion, useScroll } from "framer-motion";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import Hero3D from "../components/three/Hero3D";

const features = [
  { title: "Self-service check-in", copy: "Tap in, tap out. Your visit is logged automatically -- no more sign-in sheets." },
  { title: "Workout logging", copy: "Track every set, rep, and weight, exercise by exercise." },
  { title: "Progress tracker", copy: "Watch your lifts trend upward with visual charts over time." },
  { title: "Exercise library", copy: "Browse every muscle group and region, with form tutorials one tap away." },
  { title: "Community gallery", copy: "Share your gym moments with photos and videos." },
  { title: "Live announcements", copy: "Never miss a gym update or class change again." },
  { title: "Class schedule", copy: "See upcoming sessions and the instructors running them." },
  { title: "Consistency streaks", copy: "See your check-in streak build day by day, session by session." },
];

const stats = [
  { to: 500, suffix: "+", label: "Active members" },
  { to: 10000, suffix: "+", label: "Workouts logged" },
  { to: 73, suffix: "", label: "Exercises in the library" },
  { to: 24, suffix: "/7", label: "Access, any day" },
];

function AnimatedCounter({ to, suffix }: { to: number; suffix: string }) {
  const [value, setValue] = useState(0);
  const started = useRef(false);

  return (
    <motion.span
      onViewportEnter={() => {
        if (started.current) return;
        started.current = true;
        const duration = 1100;
        const start = performance.now();
        const tick = (now: number) => {
          const t = Math.min((now - start) / duration, 1);
          setValue(Math.round(to * (1 - Math.pow(1 - t, 3))));
          if (t < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      }}
      viewport={{ once: true, margin: "-60px" }}
    >
      {value.toLocaleString()}
      {suffix}
    </motion.span>
  );
}

export default function LandingPage() {
  const heroRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ["start start", "end start"] });

  return (
    <div className="min-h-screen overflow-x-hidden bg-[var(--color-bg)]">
      <section ref={heroRef} className="relative flex min-h-screen flex-col items-center justify-center px-4 text-center">
        <Hero3D scrollProgress={scrollYProgress} />
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

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.9 }}
          className="absolute bottom-8 left-1/2 z-10 -translate-x-1/2"
        >
          <motion.div
            animate={{ y: [0, 8, 0] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
            className="flex h-9 w-6 items-start justify-center rounded-full border-2 border-[var(--color-border)] p-1.5"
          >
            <div className="h-1.5 w-1 rounded-full bg-[var(--color-accent)]" />
          </motion.div>
        </motion.div>
      </section>

      <section className="relative border-y border-[var(--color-border)] bg-[var(--color-surface)]/60 py-12">
        <div className="mx-auto grid max-w-5xl grid-cols-2 gap-8 px-4 sm:grid-cols-4">
          {stats.map((stat) => (
            <div key={stat.label} className="text-center">
              <p className="font-display text-4xl text-[var(--color-accent)] sm:text-5xl">
                <AnimatedCounter to={stat.to} suffix={stat.suffix} />
              </p>
              <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                {stat.label}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 py-24">
        <motion.h2
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.5 }}
          className="mb-2 text-center font-display text-3xl uppercase tracking-wide text-[var(--color-text)] sm:text-4xl"
        >
          Everything your gym needs
        </motion.h2>
        <p className="mx-auto mb-10 max-w-md text-center text-sm text-[var(--color-text-muted)]">
          One app for members and staff -- from the front desk to the weight room.
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.5, delay: (i % 4) * 0.06 }}
              whileHover={{ y: -4, borderColor: "var(--color-accent)" }}
              className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
            >
              <h3 className="mb-2 font-semibold text-[var(--color-text)]">{f.title}</h3>
              <p className="text-sm text-[var(--color-text-muted)]">{f.copy}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="relative overflow-hidden px-4 py-24">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_50%,rgba(255,61,90,0.14),transparent_65%)]" />
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.96 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.6 }}
          className="relative mx-auto max-w-2xl text-center"
        >
          <h2 className="font-display text-3xl uppercase tracking-wide text-[var(--color-text)] sm:text-5xl">
            Ready to lift?
          </h2>
          <p className="mx-auto mt-3 max-w-md text-[var(--color-text-muted)]">
            Create your account and start logging today's session in under a minute.
          </p>
          <motion.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }} className="mt-8 inline-block">
            <Link
              to="/signup"
              className="rounded-md bg-[var(--color-accent)] px-8 py-3.5 text-sm font-semibold text-white hover:opacity-90"
            >
              Get Started -- It's Free
            </Link>
          </motion.div>
        </motion.div>
      </section>
    </div>
  );
}
