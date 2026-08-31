/// <reference types="vite/client" />

/** Short git sha of the tree this bundle was built from (injected by vite.config.ts). */
declare const __GIT_SHA__: string;

/** Deployment name shown in the header: dev, staging, box… (injected by vite.config.ts). */
declare const __ENVIRONMENT__: string;
