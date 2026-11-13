/** What `android/build.sh` shelved beside this build, null where nothing was (vite.config.ts). */
declare module 'virtual:android' {
  const shelved: { versionName: string; bytes: number } | null;
  export default shelved;
}
