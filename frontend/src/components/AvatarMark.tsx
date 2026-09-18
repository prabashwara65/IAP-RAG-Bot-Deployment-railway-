interface AvatarMarkProps {
  name: string;
  imageUrl: string | null;
  size?: "sm" | "lg";
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter((part) => part.length > 0);
  const first = parts[0];
  if (first === undefined) {
    return "?";
  }
  const second = parts[1];
  if (second === undefined) {
    return first.slice(0, 2).toUpperCase();
  }
  return `${first.slice(0, 1)}${second.slice(0, 1)}`.toUpperCase();
}

export function AvatarMark({ name, imageUrl, size = "sm" }: AvatarMarkProps) {
  return (
    <span className={`avatar avatar--${size}`} aria-hidden={imageUrl === null}>
      {imageUrl === null ? (
        initials(name)
      ) : (
        <img alt="" className="avatar__image" src={imageUrl} />
      )}
    </span>
  );
}
