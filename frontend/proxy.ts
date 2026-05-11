import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const PROJECT_ID_RE = /^\/projects\/([^/]+)/;

/**
 * Bench UI: route proxy.
 *
 * We only redirect routes where the bench has FULL coverage of the
 * underlying functionality. Anything not yet embedded in the bench
 * (paper editor, draft editor, files, memory, blog, portfolio, posting,
 * research roundtable detail) keeps its classic route so users don't
 * lose features. The bench surfaces themselves link to those classic
 * routes via "Open …" buttons.
 */
export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Per-project routes
  const projectMatch = pathname.match(PROJECT_ID_RE);
  if (projectMatch) {
    const projectId = projectMatch[1];

    if (projectId === 'new') {
      return NextResponse.next();
    }

    const sub = pathname.slice(projectMatch[0].length);

    // Project root + overview → bench with inspector
    if (sub === '' || sub === '/' || sub === '/overview') {
      return NextResponse.redirect(
        new URL(`/bench?project=${projectId}`, req.url),
      );
    }

    // Co-Founder chat → bench roundtable (cofounder mode)
    if (sub === '/chat') {
      return NextResponse.redirect(
        new URL(`/bench?project=${projectId}&surface=r&mode=cofounder`, req.url),
      );
    }

    // Drafts LIST only → bench drafts surface. Draft DETAIL stays classic.
    if (sub === '/drafts') {
      return NextResponse.redirect(
        new URL(`/bench?project=${projectId}&surface=d`, req.url),
      );
    }

    // Everything else under /projects/[id]/* — research, research/paper,
    // drafts/[id], blog, blog/new, blog/[id], posting, files, memory,
    // narrative, sync, timeline — stays on the classic page.
    return NextResponse.next();
  }

  // Top-level: list redirect to bench
  if (pathname === '/projects' || pathname === '/projects/') {
    return NextResponse.redirect(new URL('/bench', req.url));
  }

  // Knowledge / Worklog have full bench surfaces
  if (pathname === '/knowledge') {
    const tail = req.nextUrl.search ? `&${req.nextUrl.search.slice(1)}` : '';
    return NextResponse.redirect(new URL(`/bench?surface=k${tail}`, req.url));
  }
  if (pathname === '/worklog') {
    return NextResponse.redirect(new URL('/bench?surface=w', req.url));
  }

  // Portfolio is NOT yet embedded — stay on classic route
  // (intentionally NOT redirecting /portfolio or /portfolio/paper)

  return NextResponse.next();
}

export const config = {
  matcher: [
    '/projects',
    '/projects/:path*',
    '/knowledge',
    '/worklog',
  ],
};
