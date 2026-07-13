import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * 통계 타일 (dataviz stat tile 지침).
 *
 * 구성: label(문장형, 콜론 없음, 보조 잉크) · value(Sans semibold, 큰 글씨, 기본 잉크,
 * 비례숫자) · delta(선택, 부호 + 방향 아이콘 + 변동 텍스트).
 *
 * 색상: 값·라벨은 series 색이 아닌 ink 토큰(text-foreground/muted-foreground)을 쓴다.
 * delta 는 금융 관례상 상승=녹색/하락=적색의 방향색을 쓰되, 아이콘을 함께 제공해
 * 색상만으로 의미를 전달하지 않는다(접근성). 환율의 상승/하락은 좋고나쁨이 아니라
 * 방향일 뿐이므로 status(good/critical) 팔레트가 아닌 방향 표시로 사용한다.
 */

export type StatTileDeltaDirection = "up" | "down" | "flat";

export interface StatTileDelta {
  /** 표시 텍스트. 예: "+2.30원 (+0.17%)" 또는 "+1.52%". 부호를 포함해 전달한다. */
  text: string;
  direction: StatTileDeltaDirection;
}

export interface StatTileProps {
  label: string;
  /** 미리 포맷된 값 문자열. 예: "1,384.50". 데이터가 없으면 "—" 등을 전달한다. */
  value: string;
  /** 값 뒤에 붙는 단위. 예: "원". */
  unit?: string;
  delta?: StatTileDelta;
  className?: string;
}

const DIRECTION_META: Record<
  StatTileDeltaDirection,
  { color: string; Icon: typeof ArrowUpRight }
> = {
  up: { color: "text-[#006300] dark:text-[#0ca30c]", Icon: ArrowUpRight },
  down: { color: "text-[#d03b3b] dark:text-[#e66767]", Icon: ArrowDownRight },
  flat: { color: "text-muted-foreground", Icon: ArrowRight },
};

export default function StatTile({
  label,
  value,
  unit,
  delta,
  className,
}: StatTileProps) {
  const directionMeta = delta ? DIRECTION_META[delta.direction] : null;
  const DeltaIcon = directionMeta?.Icon;

  return (
    <Card className={cn("gap-2 px-5", className)}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold leading-tight text-foreground">
        {value}
        {unit ? (
          <span className="ml-1 text-base font-normal text-muted-foreground">
            {unit}
          </span>
        ) : null}
      </p>
      {delta && directionMeta && DeltaIcon ? (
        <p
          className={cn(
            "flex items-center gap-1 text-sm font-medium",
            directionMeta.color,
          )}
        >
          <DeltaIcon className="size-4" aria-hidden />
          <span>{delta.text}</span>
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">—</p>
      )}
    </Card>
  );
}
