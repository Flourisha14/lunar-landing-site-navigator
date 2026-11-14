interface Props { title: string; message: string }
export function ErrorPanel({ title, message }: Props) {
  return <div className="error-panel" role="alert"><strong>{title}</strong><p>{message}</p></div>;
}
