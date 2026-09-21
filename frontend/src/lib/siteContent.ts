/** The public website's marketing copy and photography.
 *
 * WHAT IS LIVE AND WHAT IS NOT. Nothing that identifies a particular gym lives
 * here any more. The name, address, phone, email, Instagram and opening hours
 * come from the Branding page (see `components/site/useGym.ts`), the brand
 * colour comes from Branding too, and the membership prices come from the Plans
 * page. Change those in the admin portal and the website follows.
 *
 * What is left below is PLACEHOLDER marketing copy: the story, the programmes,
 * the floor, the reasons, the testimonials and the figures in the About section
 * describe an example gym, and the photography is hotlinked from Unsplash. A gym
 * going live should replace these with its own. No component needs to change.
 */

/** Builds an Unsplash CDN URL at an explicit crop, so every image ships at the
 * aspect ratio its slot actually needs instead of being letterboxed by CSS. */
function photo(id: string, w: number, h: number) {
  return `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=${w}&h=${h}&q=72`;
}

/** The two labels the whole page uses for its two actions. One label per
 * intent, repeated in the nav, the hero, the plans, the closing panel and the
 * footer, so a visitor never has to work out whether two buttons differ. */
export const CTA = {
  primary: "Join the gym",
  secondary: "Book a visit",
};

export const HERO = {
  headline: ["Build more than", "muscle."],
  /** Shown only when the gym has not written a tagline on the Branding page. */
  sub: "A coached strength and conditioning gym. Serious equipment, a capped floor, and coaches who know your name.",
};

export const ABOUT = {
  headline: ["We built the gym", "we wanted to", "train in."],
  body: (gymName: string) => [
    `${gymName} was built around one rule: nobody on our floor lifts badly. The floor has grown since. The rule has not.`,
    "Every member gets a movement assessment and a written programme before they touch a barbell, and the floor is capped so the racks are free when you arrive.",
  ],
  stats: [
    { to: 9, suffix: "", label: "Years coaching" },
    { to: 40, suffix: "", label: "Members capped per floor" },
    { to: 14, suffix: "", label: "Coaches on staff" },
  ],
};

/** The disciplines band that bridges the story and the training paths. This is
 * the page's only marquee, and it exists because these are the words a visitor
 * is scanning the page for. */
export const DISCIPLINES = [
  "Strength",
  "Powerlifting",
  "Conditioning",
  "Personal training",
  "Group classes",
  "Mobility",
  "Recovery",
  "Nutrition",
];

export const PROGRAMS = [
  {
    title: "Build strength",
    weeks: "12 weeks",
    copy: "Linear progression on the big four, with accessory work chosen around your weak link.",
    image: photo("1541534741688-6078c6bfb5c5", 900, 1200),
    alt: "A lifter pressing a barbell overhead inside a rack",
  },
  {
    title: "Lose fat",
    weeks: "16 weeks",
    copy: "Lifting three days, conditioning two, and a nutrition review every fourth week.",
    image: photo("1532384748853-8f54a8f476e2", 900, 1200),
    alt: "A member working through a dumbbell set",
  },
  {
    title: "Improve endurance",
    weeks: "10 weeks",
    copy: "Zone two base work on the ergs, tempo intervals, and a tested benchmark to close.",
    image: photo("1599058917765-a780eda07a3e", 900, 1200),
    alt: "Two members training with battle ropes",
  },
  {
    title: "Athletic performance",
    weeks: "8 weeks",
    copy: "Sprint mechanics, jump work and change of direction for players in season.",
    image: photo("1550345332-09e3ac987658", 900, 1200),
    alt: "An athlete mid rope session in high contrast light",
  },
];

/** One photograph for the whole floor, and the six spaces named in type under
 * it. The six-photograph grid this replaces said less than this does. */
export const FLOOR = {
  headline: ["2,400 square feet.", "None of it wasted."],
  sub: "Six spaces on one floor, laid out so a heavy session and a first session can happen ten metres apart without either getting in the way of the other.",
  image: photo("1593079831268-3381b0db4a77", 2000, 1000),
  alt: "The main training floor, empty before opening",
  spaces: [
    { title: "Free weights", copy: "Dumbbells to 60 kg, six benches, four platforms." },
    { title: "Strength rigs", copy: "Plate loaded racks, calibrated plates, competition bars." },
    { title: "Cardio deck", copy: "Bikes, rowers and ski ergs on the mezzanine." },
    { title: "Cable floor", copy: "Selectorised machines and two dual cable stacks." },
    { title: "Recovery room", copy: "Mobility mats, guns, and two contrast baths." },
    { title: "Coaching floor", copy: "Where assessments and first sessions happen." },
  ],
};

export const REASONS = [
  {
    title: "Coaches who actually coach",
    copy: "Full time staff, every one certified in strength and conditioning. Nobody on our floor is a salesperson.",
  },
  {
    title: "Equipment that holds up",
    copy: "Competition bars, calibrated plates, proper ergs. Serviced monthly, replaced before it wears out.",
  },
  {
    title: "A floor you can get on",
    copy: "Membership is capped so the racks are free at 7pm, not just at 11am.",
  },
  {
    title: "An app that keeps you honest",
    copy: "Check in at the door, log every set, and watch your numbers move. Your coach sees them too.",
  },
  {
    title: "People who notice you missed",
    copy: "Small enough that your coach knows your name, your programme, and when you last trained.",
  },
];

export const TESTIMONIALS = [
  {
    quote:
      "I had trained for six years and never squatted properly. It took two sessions here to find out why.",
    name: "Aditya Rane",
    since: "Member since 2021",
    result: "Squat 82.5 to 147.5 kg",
  },
  {
    quote:
      "The floor cap is the whole thing. I train at seven in the evening and I have never waited for a rack.",
    name: "Marisa D'Souza",
    since: "Member since 2022",
    result: "First unassisted pull up at 41",
  },
  {
    quote: "My coach rang me the week I stopped showing up. That call is why I am still training.",
    name: "Peter Almeida",
    since: "Member since 2019",
    result: "Down 11.4 kg, off blood pressure medication",
  },
];

export const FINAL_CTA = {
  headline: ["Stop waiting.", "Start training."],
  sub: "Book a visit. Meet a coach, walk the floor, and lift something heavy before you decide.",
  image: photo("1517836357463-d25dfeac3438", 1800, 1000),
  alt: "A lifter setting up for a deadlift on the main floor",
};
