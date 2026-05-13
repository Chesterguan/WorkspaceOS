'use client';

// Soft first-run redirect: new users who haven't completed the wizard AND
// have zero projects get bumped to /onboarding. Returning users (or anyone
// who explicitly skipped via the wizard's Skip button) stay on /bench.
//
// Implemented as a one-shot check on mount — does NOT re-fire on
// subsequent project mutations to avoid bouncing the user.

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { fetchOnboardingState, type OnboardingState } from './api';
import { useProjects } from '@/lib/hooks/useProjects';

export function useFirstRunRedirect() {
  const router = useRouter();
  const checked = useRef(false);

  const { data: onboarding } = useSWR<OnboardingState>(
    '/config/onboarding/me',
    fetchOnboardingState,
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const { data: projects } = useProjects();

  useEffect(() => {
    if (checked.current) return;
    if (!onboarding || !projects) return;
    checked.current = true;

    if (!onboarding.tutorial_completed && projects.length === 0) {
      router.replace('/onboarding');
    }
  }, [onboarding, projects, router]);
}
