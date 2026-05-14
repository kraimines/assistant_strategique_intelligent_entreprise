export interface MeetingData {
  title: string;
  date: string;
  time: string;
  link: string;
  participants: { name: string; role: string; email: string; avatar: string }[];
  project: string;
  location: string;
}
