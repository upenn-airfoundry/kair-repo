'use client';

import Link from 'next/link';
import { ArrowRight, Dna, TestTube2, Lightbulb } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useEffect, useState } from 'react';
import Image from 'next/image';

const fadeInUp = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.5 }
};

const staggerContainer = {
  animate: {
    transition: {
      staggerChildren: 0.1
    }
  }
};

const headlinePart1 = [
  "Accelerating Research",
  "Transforming Science",
  "Powering Innovation",
  "Advancing Discovery"
];

const headlinePart2 = [
  "AI-Powered Insights",
  "Smart Solutions",
  "Expert Guidance",
  "Intelligent Tools"
];

const BackgroundGrid = () => {
  return (
    <div className="fixed inset-0">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]" />
    </div>
  );
};

interface ShapeProps {
  className: string;
  delay?: number;
  duration?: number;
}

const AnimatedShape = ({ className, delay = 0, duration = 20 }: ShapeProps) => {
  return (
    <motion.div
      className={`absolute ${className}`}
      animate={{
        rotate: [0, 360],
        scale: [1, 1.1, 1],
      }}
      transition={{
        duration,
        delay,
        repeat: Infinity,
        ease: "linear",
      }}
    />
  );
};

const FloatingShape = ({ className, delay = 0 }: ShapeProps) => {
  return (
    <motion.div
      className={`absolute ${className}`}
      animate={{
        y: [0, -20, 0],
        x: [0, 10, 0],
      }}
      transition={{
        duration: 5,
        delay,
        repeat: Infinity,
        ease: "easeInOut",
      }}
    />
  );
};

const DnaHelix = () => {
  return (
    <motion.div
      className="absolute right-0 top-1/4 w-64 h-64 opacity-40"
      animate={{
        rotate: [0, 360],
        scale: [1, 1.1, 1],
      }}
      transition={{
        duration: 20,
        repeat: Infinity,
        ease: "linear",
      }}
    >
      <svg viewBox="0 0 100 100" className="w-full h-full text-blue-500">
        {/* Abstract DNA strands */}
        <motion.path
          d="M30,10 C30,10 40,30 30,50 C20,70 40,90 30,90"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          animate={{
            pathLength: [0, 1],
            opacity: [0.5, 1, 0.5],
          }}
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
        <motion.path
          d="M70,10 C70,10 60,30 70,50 C80,70 60,90 70,90"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          animate={{
            pathLength: [0, 1],
            opacity: [0.5, 1, 0.5],
          }}
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
        
        {/* Minimal connecting lines */}
        {[20, 40, 60, 80].map((y, i) => (
          <motion.line
            key={i}
            x1="30"
            y1={y}
            x2="70"
            y2={y}
            stroke="currentColor"
            strokeWidth="1"
            strokeDasharray="2 2"
            animate={{
              opacity: [0.3, 0.7, 0.3],
            }}
            transition={{
              duration: 2,
              delay: i * 0.2,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
        ))}
      </svg>
    </motion.div>
  );
};

const TechCircle = () => {
  return (
    <motion.div
      className="absolute left-0 bottom-1/4 w-96 h-96 opacity-30"
      animate={{
        rotate: [0, -360],
      }}
      transition={{
        duration: 30,
        repeat: Infinity,
        ease: "linear",
      }}
    >
      <svg viewBox="0 0 100 100" className="w-full h-full text-purple-500">
        <circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" strokeWidth="1" />
        <circle cx="50" cy="50" r="35" fill="none" stroke="currentColor" strokeWidth="1" />
        <circle cx="50" cy="50" r="25" fill="none" stroke="currentColor" strokeWidth="1" />
        <circle cx="50" cy="50" r="15" fill="none" stroke="currentColor" strokeWidth="1" />
      </svg>
    </motion.div>
  );
};

const TechHexagon = () => {
  return (
    <motion.div
      className="absolute right-1/4 top-1/3 w-48 h-48 opacity-30"
      animate={{
        rotate: [0, 360],
        scale: [1, 1.1, 1],
      }}
      transition={{
        duration: 15,
        repeat: Infinity,
        ease: "linear",
      }}
    >
      <svg viewBox="0 0 100 100" className="w-full h-full text-pink-500">
        <path
          d="M50,0 L93,25 L93,75 L50,100 L7,75 L7,25 Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
        />
        <path
          d="M50,20 L80,35 L80,65 L50,80 L20,65 L20,35 Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
        />
      </svg>
    </motion.div>
  );
};

const Logo = ({ src, alt, href }: { src: string; alt: string; href: string }) => {
  return (
    <a href={href} className="text-gray-400 hover:text-gray-500">
      <span className="sr-only">{alt}</span>
      <div className="relative w-24 h-8 flex items-center">
        <Image
          src={src}
          alt={alt}
          width={96}
          height={32}
          className="object-contain w-auto h-auto"
          priority
        />
      </div>
    </a>
  );
};

const Footer = () => {
  return (
    <footer className="relative z-20">
      <div className="absolute inset-0 bg-white/40 backdrop-blur-[2px]" />
      <div className="relative mx-auto max-w-7xl px-6 py-12 md:flex md:items-center md:justify-between lg:px-8">
        <div className="flex justify-center items-center space-x-6 md:order-2 md:flex-1">
          <div className="flex items-center space-x-6">
            <Logo
              src="/images/upenn-logo.png"
              alt="University of Pennsylvania"
              href="https://www.upenn.edu"
            />
            <Logo
              src="/images/nsf-logo.png"
              alt="National Science Foundation"
              href="https://www.nsf.gov"
            />
          </div>
        </div>
        <div className="mt-6 md:order-1 md:mt-0 md:flex-1">
          <div className="flex flex-col space-y-3">
            {/* Research Links */}
            <div className="flex space-x-6">
              <a href="https://airfoundry.upenn.edu/research/" className="text-sm text-gray-500 hover:text-gray-900">
                Research Overview
              </a>
              <a href="https://airfoundry.upenn.edu/research/projects/" className="text-sm text-gray-500 hover:text-gray-900">
                Projects
              </a>
              <a href="https://airfoundry.upenn.edu/research/publications/" className="text-sm text-gray-500 hover:text-gray-900">
                Publications
              </a>
              <a href="https://airfoundry.upenn.edu/research/team/" className="text-sm text-gray-500 hover:text-gray-900">
                Team
              </a>
            </div>
            {/* Copyright */}
            <p className="text-sm text-gray-500">
              © {new Date().getFullYear()} AIRFoundry. All rights reserved.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default function Home() {
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const [part1Index, setPart1Index] = useState(0);
  const [part2Index, setPart2Index] = useState(0);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePosition({
        x: (e.clientX / window.innerWidth - 0.5) * 20,
        y: (e.clientY / window.innerHeight - 0.5) * 20,
      });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  useEffect(() => {
    const interval1 = setInterval(() => {
      setPart1Index((prev) => (prev + 1) % headlinePart1.length);
    }, 3000);

    const interval2 = setInterval(() => {
      setPart2Index((prev) => (prev + 1) % headlinePart2.length);
    }, 3000);

    return () => {
      clearInterval(interval1);
      clearInterval(interval2);
    };
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-gray-50 overflow-hidden">
      {/* Background Elements */}
      <div className="fixed inset-0 pointer-events-none">
        {/* Grid Background */}
        <BackgroundGrid />
        
        {/* Animated Shapes */}
        <div className="absolute inset-0">
          {/* Abstract Shapes */}
          <AnimatedShape className="w-32 h-32 border-2 border-blue-200 rounded-full top-1/4 left-1/4 opacity-50" />
          <AnimatedShape className="w-24 h-24 border-2 border-purple-200 rounded-lg top-1/3 right-1/4 opacity-50" delay={2} />
          <AnimatedShape className="w-40 h-40 border-2 border-pink-200 rounded-full bottom-1/4 left-1/3 opacity-50" delay={4} />
          
          {/* Floating Elements */}
          <FloatingShape className="w-16 h-16 border-2 border-blue-100 rounded-full top-1/2 left-1/4 opacity-50" />
          <FloatingShape className="w-20 h-20 border-2 border-purple-100 rounded-lg top-1/3 right-1/3 opacity-50" delay={1} />
          <FloatingShape className="w-12 h-12 border-2 border-pink-100 rounded-full bottom-1/3 right-1/4 opacity-50" delay={2} />
          
          {/* Tech-themed Elements */}
          <DnaHelix />
          <TechCircle />
          <TechHexagon />
          
          {/* Gradient Orbs */}
          <motion.div
            className="absolute inset-0"
            animate={{
              x: mousePosition.x,
              y: mousePosition.y,
            }}
            transition={{
              type: "spring",
              damping: 30,
              stiffness: 200,
            }}
          >
            <div className="absolute w-[500px] h-[500px] bg-blue-100 rounded-full mix-blend-multiply filter blur-xl opacity-70 -top-40 -right-40" />
            <div className="absolute w-[500px] h-[500px] bg-purple-100 rounded-full mix-blend-multiply filter blur-xl opacity-70 -bottom-40 -left-40" />
            <div className="absolute w-[500px] h-[500px] bg-pink-100 rounded-full mix-blend-multiply filter blur-xl opacity-70 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
          </motion.div>
        </div>

        {/* Subtle Gradient Overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-white/20 via-transparent to-white/20" />
      </div>

      {/* Content */}
      <div className="relative z-10">
        {/* Hero Section */}
        <motion.div 
          className="relative isolate px-6 pt-14 lg:px-8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8 }}
        >
          <div className="mx-auto max-w-2xl py-32 sm:py-48 lg:py-56">
            <motion.div 
              className="text-center"
              variants={staggerContainer}
              initial="initial"
              animate="animate"
            >
              <motion.h1 
                className="text-4xl font-bold tracking-tight text-gray-900 sm:text-6xl"
                variants={fadeInUp}
              >
                <div className="h-[1.2em] min-h-[1.2em] overflow-hidden flex items-center justify-center">
                  <AnimatePresence mode="wait">
                    <motion.span
                      key={part1Index}
                      initial={{ y: 20, opacity: 0 }}
                      animate={{ y: 0, opacity: 1 }}
                      exit={{ y: -20, opacity: 0 }}
                      transition={{ duration: 0.5 }}
                      className="inline-block"
                    >
                      {headlinePart1[part1Index]}
                    </motion.span>
                  </AnimatePresence>
                </div>
                {' '}with{' '}
                <span className="text-blue-600 relative">
                  <div className="h-[1.2em] min-h-[1.2em] overflow-hidden flex items-center justify-center">
                    <AnimatePresence mode="wait">
                      <motion.span
                        key={part2Index}
                        initial={{ y: 20, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        exit={{ y: -20, opacity: 0 }}
                        transition={{ duration: 0.5 }}
                        className="inline-block"
                      >
                        {headlinePart2[part2Index]}
                      </motion.span>
                    </AnimatePresence>
                  </div>
                  <motion.div
                    className="absolute -bottom-2 left-0 w-full h-1 bg-blue-600"
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ delay: 0.5, duration: 0.5 }}
                  />
                </span>
              </motion.h1>
              <motion.p 
                className="mt-6 text-lg leading-8 text-gray-600"
                variants={fadeInUp}
              >
                KAIR combines expert knowledge with advanced AI to streamline RNA synthesis and delivery projects. Our platform learns from your research patterns, providing contextual insights and accelerating your scientific discoveries.
              </motion.p>
              <motion.div 
                className="mt-10 flex items-center justify-center gap-x-6"
                variants={fadeInUp}
              >
                <Link
                  href="/login"
                  className="group rounded-md bg-blue-600 px-3.5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 transition-all duration-300"
                >
                  Develop RNA solutions!
                  <ArrowRight className="ml-2 -mr-1 h-4 w-4 inline group-hover:translate-x-1 transition-transform" />
                </Link>
                <Link 
                  href="/chat" 
                  className="text-sm font-semibold leading-6 text-gray-900 hover:text-blue-600 transition-colors duration-300"
                >
                  Explore Platform <span aria-hidden="true" className="inline-block group-hover:translate-x-1 transition-transform">→</span>
                </Link>
              </motion.div>
            </motion.div>
          </div>
        </motion.div>

        {/* Features Section */}
        <motion.div 
          className="py-24 sm:py-32"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
        >
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            <motion.div 
              className="mx-auto max-w-2xl lg:text-center"
              variants={staggerContainer}
              initial="initial"
              whileInView="animate"
              viewport={{ once: true }}
            >
              <motion.h2 
                className="text-base font-semibold leading-7 text-blue-600"
                variants={fadeInUp}
              >
                Research Innovation
              </motion.h2>
              <motion.p 
                className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl"
                variants={fadeInUp}
              >
                Advancing RNA Research Through AI
              </motion.p>
            </motion.div>
            <motion.div 
              className="mx-auto mt-16 max-w-2xl sm:mt-20 lg:mt-24 lg:max-w-none"
              variants={staggerContainer}
              initial="initial"
              whileInView="animate"
              viewport={{ once: true }}
            >
              <dl className="grid max-w-xl grid-cols-1 gap-x-8 gap-y-16 lg:max-w-none lg:grid-cols-3">
                {[
                  {
                    icon: Dna,
                    title: "Expert-Informed AI",
                    description: "Leverage AI tools trained on expert knowledge to create and optimize RNA synthesis pipelines."
                  },
                  {
                    icon: TestTube2,
                    title: "Dynamic Knowledge Base",
                    description: "Access continuously updated reviews and insights in RNA synthesis and delivery research."
                  },
                  {
                    icon: Lightbulb,
                    title: "Contextual Learning",
                    description: "Our platform learns from your research patterns to provide personalized, relevant insights."
                  }
                ].map((feature, _) => {
                  const Icon = feature.icon;
                  return (
                    <motion.div 
                      key={feature.title}
                      className="flex flex-col"
                      variants={fadeInUp}
                      whileHover={{ scale: 1.05 }}
                      transition={{ type: "spring", stiffness: 300 }}
                    >
                      <dt className="flex items-center gap-x-3 text-base font-semibold leading-7 text-gray-900">
                        <Icon className="h-5 w-5 flex-none text-blue-600" />
                        {feature.title}
                      </dt>
                      <dd className="mt-4 flex flex-auto flex-col text-base leading-7 text-gray-600">
                        <p className="flex-auto">{feature.description}</p>
                      </dd>
                    </motion.div>
                  );
                })}
              </dl>
            </motion.div>
          </div>
        </motion.div>

        {/* CTA Section */}
        <motion.div 
          className="bg-white"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
        >
          <div className="mx-auto max-w-7xl py-24 sm:px-6 sm:py-32 lg:px-8">
            <motion.div 
              className="relative isolate overflow-hidden bg-gray-900 px-6 py-24 text-center shadow-2xl sm:rounded-3xl sm:px-16"
              whileHover={{ scale: 1.02 }}
              transition={{ type: "spring", stiffness: 300 }}
            >
              <motion.h2 
                className="mx-auto max-w-2xl text-3xl font-bold tracking-tight text-white sm:text-4xl"
                variants={fadeInUp}
                initial="initial"
                whileInView="animate"
                viewport={{ once: true }}
              >
                Ready to Transform Your RNA Research?
              </motion.h2>
              <motion.p 
                className="mx-auto mt-6 max-w-xl text-lg leading-8 text-gray-300"
                variants={fadeInUp}
                initial="initial"
                whileInView="animate"
                viewport={{ once: true }}
              >
                Join the future of AI-augmented research. Experience how KAIR can accelerate your RNA synthesis and delivery projects.
              </motion.p>
              <motion.div 
                className="mt-10 flex items-center justify-center gap-x-6"
                variants={fadeInUp}
                initial="initial"
                whileInView="animate"
                viewport={{ once: true }}
              >
                <Link
                  href="/login"
                  className="group rounded-md bg-white px-3.5 py-2.5 text-sm font-semibold text-gray-900 shadow-sm hover:bg-gray-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white transition-all duration-300"
                >
                  Start Researching
                  <ArrowRight className="ml-2 -mr-1 h-4 w-4 inline group-hover:translate-x-1 transition-transform" />
                </Link>
                <Link 
                  href="/chat" 
                  className="text-sm font-semibold leading-6 text-white hover:text-gray-300 transition-colors duration-300"
                >
                  Learn More <span aria-hidden="true" className="inline-block group-hover:translate-x-1 transition-transform">→</span>
                </Link>
              </motion.div>
            </motion.div>
          </div>
        </motion.div>
      </div>

      {/* Add Footer */}
      <Footer />
    </div>
  );
}
