import { cn } from "../utils"

const tutorDexLogoUrl = "/TutorDex-icon-128.png"

export function TutorDexLogo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <img src={tutorDexLogoUrl} alt="TutorDex" className="h-9 w-9 rounded-xl object-contain" />
      <span className="font-bold text-xl">TutorDex</span>
    </div>
  )
}
