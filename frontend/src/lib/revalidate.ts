/**
 * Telling surfaces that something they showed is no longer true.
 *
 * The bug this exists to remove: Vita and the place detail each fetched into
 * their own `useState`, so deleting a place on one screen left the other
 * showing it until somebody reloaded the browser. Two private copies of the
 * same fact, and no way for a mutation to reach either.
 *
 * This is deliberately **not** a store. It holds no data and answers no
 * queries — it holds a number per resource and lets a screen know when that
 * number changed. Each surface still owns its own fetch, which is the pattern
 * this codebase already uses; what it gains is a way to be told that its copy
 * is stale.
 *
 *     mutation → server success → invalidate(resource) → subscribers refetch
 *
 * A store would mean two sources of truth for the same places: the server and
 * a cache that has to be kept honest. The server stays the only one.
 */
import { useEffect, useRef, useState } from 'react';

/** The things a mutation can make stale. Names match the API surfaces. */
export type Resource =
  | 'places:list'
  | 'presence:current'
  | `place:${string}`;

type Listener = () => void;

const versions = new Map<string, number>();
const listeners = new Map<string, Set<Listener>>();

function bump(resource: string): void {
  versions.set(resource, (versions.get(resource) ?? 0) + 1);
  listeners.get(resource)?.forEach((notify) => {
    try {
      notify();
    } catch {
      /* a listener that throws must not stop the others being told */
    }
  });
}

/**
 * Mark resources stale after a mutation the server accepted.
 *
 * Called only on success. An optimistic invalidation after a failed delete
 * would hide the place from a list it is still in — the person would think it
 * was gone, and find it again tomorrow.
 */
export function invalidate(...resources: Resource[]): void {
  for (const resource of resources) bump(resource);
}

/**
 * Everything a change to one place touches.
 *
 * Kept in one function so a new surface is added once rather than remembered
 * at every call site. Presence is included because a deleted place cannot go
 * on being where somebody is.
 */
export function invalidatePlace(placeId?: string): void {
  const resources: Resource[] = ['places:list', 'presence:current'];
  if (placeId) resources.push(`place:${placeId}`);
  invalidate(...resources);
}

/**
 * Re-run `refetch` whenever one of these resources is invalidated.
 *
 * Not on mount: the caller already loads once, and firing here too would mean
 * two requests for every screen. This only reacts to change.
 */
export function useRevalidate(resources: Resource[], refetch: () => void): void {
  const latest = useRef(refetch);
  latest.current = refetch;

  const key = resources.join('|');
  useEffect(() => {
    const notify = () => latest.current();
    const set = resources.map((resource) => {
      const existing = listeners.get(resource) ?? new Set<Listener>();
      existing.add(notify);
      listeners.set(resource, existing);
      return resource;
    });
    return () => {
      for (const resource of set) listeners.get(resource)?.delete(notify);
    };
    // `key` is the stable identity of the list; the array itself is new each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}

/** The current version of a resource, for tests and for debugging. */
export function versionOf(resource: Resource): number {
  return versions.get(resource) ?? 0;
}

/** Test helper: forget every subscription and version. */
export function reset(): void {
  versions.clear();
  listeners.clear();
}

/**
 * A hook shape for surfaces that would rather re-render than call a function.
 * Unused by the current screens; kept because it is the obvious next need.
 */
export function useVersion(resource: Resource): number {
  const [version, setVersion] = useState(() => versionOf(resource));
  useRevalidate([resource], () => setVersion(versionOf(resource)));
  return version;
}
